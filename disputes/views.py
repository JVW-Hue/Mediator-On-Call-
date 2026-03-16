from datetime import timedelta

from django.shortcuts import (
    render,
    redirect,
    get_object_or_404,
)
from django.contrib import messages
from django.utils import timezone

from .forms import (
    DisputeForm,
    DisputeDocumentFormSet,
    RespondentResponseForm,
    ResponseDocumentFormSet,
)
from .models import Dispute, DisputeDocument, RespondentResponse, AuditLog


def _send_notification(task_func, *args, **kwargs):
    """Try async (Celery), fall back to sync if Celery unavailable."""
    try:
        task_func.delay(*args, **kwargs)
    except Exception:
        try:
            task_func(*args, **kwargs)
        except Exception:
            pass


try:
    from ratelimit.decorators import ratelimit

    _apply_decorators = [ratelimit(key="ip", rate="5/h", method="POST")]
    _respond_decorators = [ratelimit(key="ip", rate="5/h", method="POST")]
except ImportError:
    _apply_decorators = []
    _respond_decorators = []


def _apply_view(request):
    if request.method == "POST":
        form = DisputeForm(request.POST)
        formset = DisputeDocumentFormSet(
            request.POST, request.FILES, queryset=DisputeDocument.objects.none()
        )
        if form.is_valid() and formset.is_valid():
            # Check for potential duplicate
            applicant_cell = form.cleaned_data.get('applicant_cell', '')
            applicant_name = form.cleaned_data.get('applicant_name', '')
            applicant_surname = form.cleaned_data.get('applicant_surname', '')
            
            # Check if similar dispute exists
            existing = Dispute.objects.filter(
                applicant_cell=applicant_cell,
                applicant_name__iexact=applicant_name,
                applicant_surname__iexact=applicant_surname,
                status__in=['submitted', 'forwarded', 'responded', 'mediation_scheduled']
            ).first()
            
            if existing:
                messages.warning(request, "A similar dispute has already been submitted. Please contact us if this is a new dispute.")
            
            dispute = form.save()
            AuditLog.objects.create(
                dispute=dispute,
                user=None,
                action="Dispute submitted",
            )
            documents = formset.save(commit=False)
            for doc in documents:
                doc.dispute = dispute
                doc.save()
            
            # Automatically reject family, labour, or property disputes
            INELIGIBLE_TYPES = ['family', 'labour', 'property']
            if dispute.dispute_type in INELIGIBLE_TYPES:
                dispute.status = "rejected"
                dispute.is_mediatable = False
                dispute.screening_notes = f"Automatic rejection: {dispute.get_dispute_type_display()} disputes are not eligible for mediation under South African law."
                dispute.save()
                AuditLog.objects.create(
                    dispute=dispute,
                    user=None,
                    action=f"Dispute auto-rejected - {dispute.get_dispute_type_display()} not eligible",
                )
                messages.warning(request, f"Your dispute involves {dispute.get_dispute_type_display()} matters which are not eligible for mediation. Your file has been closed.")
                return render(request, "disputes/rejected_not_eligible.html", {"dispute": dispute})
            
            messages.success(request, "Thank you! Your dispute has been submitted successfully. We will review your case and contact you shortly.")
            return redirect("disputes:application_success")
    else:
        form = DisputeForm()
        formset = DisputeDocumentFormSet(queryset=DisputeDocument.objects.none())
    return render(
        request,
        "disputes/apply.html",
        {"form": form, "formset": formset},
    )


# Apply rate limit decorators (if django-ratelimit installed)
for dec in reversed(_apply_decorators):
    _apply_view = dec(_apply_view)

apply_view = _apply_view


def success_view(request):
    return render(request, "disputes/success.html")


def _respond_view(request, token):
    dispute = get_object_or_404(Dispute, respondent_token=token)

    # 30‑day expiry & closed/rejected guard
    if dispute.status in {"closed", "rejected"} or dispute.token_created_at < (
        timezone.now() - timedelta(days=30)
    ):
        return render(
            request,
            "disputes/respond_expired.html",
            {"dispute": dispute},
        )

    from .forms import ResponseDocumentFormSet  # avoid circular import in type checkers

    if request.method == "POST":
        form = RespondentResponseForm(request.POST)
        existing_response = getattr(dispute, "response", None)
        base_qs = existing_response.documents.all() if existing_response else None
        formset = ResponseDocumentFormSet(
            request.POST,
            request.FILES,
            queryset=base_qs if base_qs is not None else ResponseDocumentFormSet().queryset.none(),
        )
        if form.is_valid() and formset.is_valid():
            response, _created = RespondentResponse.objects.get_or_create(
                dispute=dispute
            )
            response.consent_to_mediate = form.cleaned_data["consent_to_mediate"]
            response.agreed_to_rules = form.cleaned_data["agreed_to_rules"]
            response.defence_explanation = form.cleaned_data["defence_explanation"]
            response.save()

            documents = formset.save(commit=False)
            for doc in documents:
                doc.response = response
                doc.save()

            dispute.status = "responded"
            dispute.save(update_fields=["status"])

            AuditLog.objects.create(
                dispute=dispute,
                user=None,
                action="Respondent submitted response",
            )

            # Notify applicant with a link to view defence
            from .tasks import notify_recipient

            view_url = request.build_absolute_uri(
                redirect(
                    "disputes:view_defence",
                    token=dispute.applicant_view_token,
                ).url
            )
            if dispute.applicant_cell:
                _send_notification(
                    notify_recipient,
                    to=dispute.applicant_cell,
                    body=(
                        "Respondent has agreed to mediate and filed a defence. "
                        f"View details: {view_url}"
                    ),
                )

            messages.success(request, "Your response has been submitted.")
            return render(
                request,
                "disputes/respond_success.html",
                {"dispute": dispute},
            )
    else:
        existing_response = getattr(dispute, "response", None)
        initial = {}
        if existing_response:
            initial = {
                "consent_to_mediate": existing_response.consent_to_mediate,
                "agreed_to_rules": existing_response.agreed_to_rules,
                "defence_explanation": existing_response.defence_explanation,
            }
        form = RespondentResponseForm(initial=initial)
        base_qs = existing_response.documents.all() if existing_response else None
        formset = ResponseDocumentFormSet(
            queryset=base_qs if base_qs is not None else ResponseDocumentFormSet().queryset.none()
        )

    return render(
        request,
        "disputes/respond.html",
        {"dispute": dispute, "form": form, "formset": formset},
    )


for dec in reversed(_respond_decorators):
    _respond_view = dec(_respond_view)

respond_view = _respond_view


def view_defence(request, token):
    dispute = get_object_or_404(Dispute, applicant_view_token=token)
    response = getattr(dispute, "response", None)
    if not response:
        return render(
            request,
            "disputes/defence_unavailable.html",
            {"dispute": dispute},
        )
    return render(
        request,
        "disputes/view_defence.html",
        {"dispute": dispute, "response": response},
    )


def view_outcome(request, token):
    dispute = get_object_or_404(Dispute, applicant_view_token=token)
    if not hasattr(dispute, "mediation"):
        return render(
            request,
            "disputes/outcome_unavailable.html",
            {"dispute": dispute},
        )
    session = dispute.mediation
    return render(
        request,
        "disputes/view_outcome.html",
        {"dispute": dispute, "session": session},
    )
