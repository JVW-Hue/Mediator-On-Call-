from datetime import datetime, timedelta
import io
import json
import zipfile
from functools import wraps

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView

from disputes.models import Dispute, MediationSession, Mediator, AuditLog, MediatableCase, ReferredCase
from disputes.tasks import notify_recipient
from disputes.forms import MediationOutcomeForm


def _send_notification(task_func, *args, **kwargs):
    """Try async (Celery), fall back to sync if Celery unavailable."""
    try:
        task_func.delay(*args, **kwargs)
    except Exception:
        try:
            task_func(*args, **kwargs)
        except Exception:
            pass


def mediator_required(view_func):
    """Decorator to require user has a Mediator profile."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return auth_views.LoginView.as_view()(request, *args, **kwargs)
        if not hasattr(request.user, 'mediator'):
            return redirect('no_access')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


class CustomLoginView(auth_views.LoginView):
    template_name = 'registration/login.html'
    
    def form_valid(self, form):
        remember_me = self.request.POST.get('remember_me')
        if remember_me:
            self.request.session.set_expiry(60 * 60 * 24 * 30)  # 30 days
        else:
            self.request.session.set_expiry(0)  # Session expires when browser closes
        return super().form_valid(form)

    def get_success_url(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return '/dashboard/'
        try:
            mediator = Mediator.objects.get(user=user)
            return '/dashboard/mediator/'
        except Mediator.DoesNotExist:
            return '/no-access/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['noaccess'] = self.request.GET.get('noaccess')
        return context


def no_access(request):
    return render(request, 'registration/no_access.html')


def signup(request):
    from django.contrib.auth import get_user_model
    from django import forms
    from disputes.models import Mediator
    
    User = get_user_model()
    
    class SignupForm(forms.Form):
        username = forms.CharField(max_length=150)
        email = forms.EmailField()
        password1 = forms.CharField(widget=forms.PasswordInput, label="Password")
        password2 = forms.CharField(widget=forms.PasswordInput, label="Confirm Password")
        user_type = forms.ChoiceField(choices=[('mediator', 'Mediator'), ('staff', 'Staff')], label="I am a:")
        cell = forms.CharField(max_length=20, required=False, label="Cell Phone Number")
        
        def clean_username(self):
            username = self.cleaned_data['username']
            if User.objects.filter(username=username).exists():
                raise forms.ValidationError("Username already exists")
            return username
        
        def clean(self):
            cleaned_data = super().clean()
            if cleaned_data.get('password1') != cleaned_data.get('password2'):
                raise forms.ValidationError("Passwords do not match")
            return cleaned_data
    
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user_type = form.cleaned_data['user_type']
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password1'],
                is_staff=(user_type == 'staff')
            )
            
            if user_type == 'mediator':
                cell = form.cleaned_data.get('cell', '')
                Mediator.objects.create(user=user, cell=cell)
            
            from django.contrib.auth import authenticate, login
            user = authenticate(username=form.cleaned_data['username'], password=form.cleaned_data['password1'])
            if user:
                login(request, user)
                if user.is_staff:
                    return redirect('dashboard:admin_home')
                else:
                    return redirect('dashboard:mediator_home')
    else:
        form = SignupForm()
    
    return render(request, 'registration/signup.html', {'form': form})


@method_decorator(staff_member_required, name="dispatch")
class AdminDashboardView(TemplateView):
    template_name = "dashboard/admin_home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_disputes"] = Dispute.objects.count()
        context["pending_screening"] = Dispute.objects.filter(status="submitted").count()
        context["active_mediations"] = Dispute.objects.filter(
            status="mediation_scheduled"
        ).count()
        context["closed_cases"] = Dispute.objects.filter(status="closed").count()
        context["referred_cases"] = ReferredCase.objects.count()
        context["mediatable_cases"] = MediatableCase.objects.count()

        type_counts = Dispute.objects.values("dispute_type").annotate(count=Count("id"))
        context["type_labels"] = [t["dispute_type"] for t in type_counts]
        context["type_data"] = [t["count"] for t in type_counts]

        context["recent_disputes"] = Dispute.objects.order_by("-created_at")[:10]
        context["upcoming_sessions"] = MediationSession.objects.filter(
            scheduled_at__gte=timezone.now()
        ).order_by("scheduled_at")[:5]

        sessions = MediationSession.objects.filter(
            scheduled_at__gte=timezone.now() - timedelta(days=30)
        ).select_related("dispute", "mediator__user")
        context["calendar_events"] = [
            {
                "title": f"Dispute #{s.dispute.id} - {s.mediator.user.get_full_name() or s.mediator.user.username}",
                "start": s.scheduled_at.isoformat(),
                "url": reverse("dashboard:dispute_detail", args=[s.dispute.id]),
                "backgroundColor": "#198754" if s.dispute.status == "mediation_scheduled" else "#0d6efd",
            }
            for s in sessions
        ]
        return context


@method_decorator(staff_member_required, name="dispatch")
class DisputeListView(ListView):
    model = Dispute
    template_name = "dashboard/dispute_list.html"
    context_object_name = "disputes"
    paginate_by = 50

    def get_queryset(self):
        queryset = super().get_queryset()
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Mark duplicates (same applicant name + cell)
        from django.db.models import Count
        duplicates = Dispute.objects.values('applicant_cell').annotate(
            count=Count('id')
        ).filter(count__gt=1).values_list('applicant_cell', flat=True)
        
        queryset = queryset.annotate(
            is_duplicate=Count('id', filter=models.Q(applicant_cell__in=duplicates))
        )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["mediators"] = Mediator.objects.select_related("user").all()
        context["current_status"] = self.request.GET.get('status', '')
        
        # Check if any duplicates exist
        from django.db.models import Count
        duplicates = Dispute.objects.values('applicant_cell').annotate(
            count=Count('id')
        ).filter(count__gt=1).exists()
        context["duplicates_exist"] = duplicates
        
        return context


@staff_member_required
def delete_dispute(request, pk):
    dispute = get_object_or_404(Dispute, pk=pk)
    dispute.delete()
    messages.success(request, f"Dispute #{pk} deleted successfully.")
    return redirect("dashboard:dispute_list")


@method_decorator(staff_member_required, name="dispatch")
class DisputeDetailView(DetailView):
    model = Dispute
    template_name = "dashboard/dispute_detail.html"
    context_object_name = "dispute"


@staff_member_required
@require_POST
def screen_dispute(request):
    dispute_id = request.POST.get("dispute_id")
    decision = request.POST.get("decision")
    notes = request.POST.get("notes", "")
    offer_foresolve = request.POST.get("offer_foresolve") == "on"
    refer_to = request.POST.get("refer_to", "")
    refer_notes = request.POST.get("refer_notes", "")
    
    if not dispute_id:
        messages.error(request, "No dispute selected. Please try again.")
        return redirect("dashboard:dispute_list")
    
    try:
        dispute = Dispute.objects.get(id=dispute_id, status="submitted")
    except Dispute.DoesNotExist:
        messages.error(request, "Dispute not found or already processed.")
        return redirect("dashboard:dispute_list")

    if decision == "accept":
        dispute.is_mediatable = True
        dispute.status = "forwarded"
        dispute.screening_notes = notes
        dispute.screened_by = request.user
        dispute.screened_at = timezone.now()
        dispute.save()

        MediatableCase.objects.create(
            dispute=dispute,
            accepted_by=request.user,
            notes=notes,
        )

        respondent_link = request.build_absolute_uri(
            reverse("disputes:respond", args=[str(dispute.respondent_token)])
        )
        respondent_cell = dispute.respondent_cell or dispute.business_cell
        if respondent_cell:
            _send_notification(
                notify_recipient,
                to=respondent_cell,
                body=f"A dispute has been filed against you. Please respond here: {respondent_link}",
            )

        if dispute.applicant_cell:
            _send_notification(
                notify_recipient,
                to=dispute.applicant_cell,
                body="Your dispute has been accepted and forwarded to the respondent. They will receive a link to respond.",
            )

        AuditLog.objects.create(
            dispute=dispute,
            user=request.user,
            action="Dispute accepted and forwarded to respondent",
        )

        messages.success(request, f"Dispute #{dispute_id} accepted and forwarded.")
    else:
        dispute.is_mediatable = False
        dispute.status = "rejected"
        if refer_to:
            dispute.screening_notes = f"REFERRED TO: {refer_to.upper()}. Notes: {notes}. Referral details: {refer_notes}"
        else:
            dispute.screening_notes = notes

        if refer_to or offer_foresolve:
            referral_type = "foresolve" if offer_foresolve else refer_to
            ReferredCase.objects.update_or_create(
                dispute=dispute,
                defaults={
                    "referred_to": referral_type,
                    "referred_by": request.user,
                    "notes": notes,
                    "referral_details": refer_notes,
                },
            )
        
        # Send email to applicant
        if dispute.applicant_email:
            from django.core.mail import send_mail
            from django.conf import settings
            
            if offer_foresolve:
                subject = f"Update regarding your Mediation Application - Case #{dispute.id}"
                body = f"""Dear {dispute.applicant_name} {dispute.applicant_surname},

Thank you for submitting your dispute to Mediators on Call for mediation.

After reviewing your request, we have found that the dispute cannot be mediated through our pro bono service. However, through our Foresolve process, we are able to divert your dispute for further consideration and possible resolution.

Further direction shall be provided to you shortly.

Your mediation request through Pro Bono NPC has been closed.

If you have any questions, please contact us.

Best regards,
Mediators on Call Team
"""
            elif refer_to:
                refer_name = refer_to.upper()
                subject = f"Update regarding your Mediation Application - Case #{dispute.id}"
                body = f"""Dear {dispute.applicant_name} {dispute.applicant_surname},

Thank you for submitting your dispute to Mediators on Call for mediation.

Your dispute has been reviewed and has been referred to {refer_name} for further handling. You will be contacted by the relevant department shortly.

Your file with Mediators on Call has been closed.

If you have any questions about the referral, please contact {refer_name} directly.

Best regards,
Mediators on Call Team
"""
            else:
                subject = f"Update regarding your Mediation Application - Case #{dispute.id}"
                body = f"""Dear {dispute.applicant_name} {dispute.applicant_surname},

Thank you for submitting your dispute to Mediators on Call for mediation.

After reviewing your request, we have found that the dispute cannot be mediated through our pro bono service. Your file has been closed.

We encourage you to seek alternative dispute resolution methods that may be more suitable for your situation.

If you have any questions, please contact us.

Best regards,
Mediators on Call Team
"""
            
            try:
                send_mail(
                    subject,
                    body,
                    settings.DEFAULT_FROM_EMAIL,
                    [dispute.applicant_email],
                    fail_silently=False,
                )
            except Exception as e:
                # Log error but don't stop the process
                import logging
                logging.error(f"Failed to send rejection email: {e}")

        # Send SMS notification
        if dispute.applicant_cell:
            if offer_foresolve:
                sms_body = (
                    "After reviewing your request we have found that the dispute cannot be mediated. "
                    "However, through our Foresolve process we are able to divert your dispute for further "
                    "consideration and possible resolution. Further direction shall be provided. "
                    "Your mediation request through Pro Bono NPC has been closed."
                )
            elif refer_to:
                refer_name = refer_to.upper()
                sms_body = (
                    f"Your dispute has been reviewed and has been referred to {refer_name} for further handling. "
                    "You will be contacted by the relevant department shortly."
                )
            else:
                sms_body = (
                    "After reviewing your request we have found that the dispute cannot be mediated. "
                    "Your file has been closed."
                )
            _send_notification(notify_recipient, to=dispute.applicant_cell, body=sms_body)

        AuditLog.objects.create(
            dispute=dispute,
            user=request.user,
            action=f"Dispute rejected - referred to {refer_to}" if refer_to else "Dispute rejected - not mediatable",
        )

        messages.warning(request, f"Dispute #{dispute_id} rejected and applicant notified.")

    return redirect("dashboard:dispute_list")


@staff_member_required
@require_POST
def assign_mediator(request):
    dispute_id = request.POST.get("dispute_id")
    mediator_id = request.POST.get("mediator_id")
    scheduled_at_str = request.POST.get("scheduled_at")

    dispute = get_object_or_404(Dispute, id=dispute_id, status__in=["responded", "ready_for_assignment"])
    mediator = get_object_or_404(Mediator, id=mediator_id)

    try:
        scheduled_at = datetime.fromisoformat(scheduled_at_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        scheduled_at = datetime.fromisoformat(scheduled_at_str)
    if timezone.is_naive(scheduled_at):
        scheduled_at = timezone.make_aware(scheduled_at, timezone.utc)

    respondent_name = (
        f"{dispute.respondent_name or ''} {dispute.respondent_surname or ''}".strip()
        or dispute.business_name
    )
    topic = f"Mediation: Dispute #{dispute.id} - {dispute.applicant_name} vs {respondent_name}"

    from disputes.zoom import create_zoom_meeting

    join_url, host_url = create_zoom_meeting(topic, scheduled_at)

    if not join_url:
        messages.error(
            request,
            "Zoom meeting creation failed. Create the session manually in admin or check Zoom credentials.",
        )
        return redirect("dashboard:dispute_list")

    MediationSession.objects.create(
        dispute=dispute,
        mediator=mediator,
        scheduled_at=scheduled_at,
        zoom_link=join_url,
    )

    dispute.status = "mediation_scheduled"
    dispute.save(update_fields=["status"])

    dt_str = scheduled_at.strftime("%Y-%m-%d %H:%M") + " UTC"
    mediator_name = mediator.user.get_full_name() or mediator.user.username

    applicant_msg = (
        f"Your mediation has been scheduled. Mediator: {mediator_name}, "
        f"Date: {dt_str}, Join link: {join_url}"
    )
    respondent_msg = (
        f"Mediation scheduled for your dispute. Mediator: {mediator_name}, "
        f"Date: {dt_str}, Join link: {join_url}"
    )
    mediator_msg = (
        f"New mediation assigned: Dispute #{dispute.id}, Date: {dt_str}, "
        f"Host link: {host_url or join_url}"
    )

    if dispute.applicant_cell:
        _send_notification(notify_recipient, to=dispute.applicant_cell, body=applicant_msg)
    respondent_cell = dispute.respondent_cell or dispute.business_cell
    if respondent_cell:
        _send_notification(notify_recipient, to=respondent_cell, body=respondent_msg)
    if mediator.cell:
        _send_notification(notify_recipient, to=mediator.cell, body=mediator_msg)

    AuditLog.objects.create(
        dispute=dispute,
        user=request.user,
        action=f"Mediation scheduled with {mediator_name} for {dt_str}",
    )

    messages.success(
        request, f"Mediator assigned and notifications sent for dispute #{dispute_id}."
    )
    return redirect("dashboard:dispute_list")


@login_required
@mediator_required
def mediator_dashboard(request):
    mediator = get_object_or_404(Mediator, user=request.user)
    upcoming = MediationSession.objects.filter(
        mediator=mediator,
        scheduled_at__gte=timezone.now(),
    ).order_by("scheduled_at")
    past = MediationSession.objects.filter(
        mediator=mediator,
        scheduled_at__lt=timezone.now(),
    ).order_by("-scheduled_at")
    return render(
        request,
        "dashboard/mediator_home.html",
        {"upcoming": upcoming, "past": past, "mediator": mediator},
    )


@login_required
@mediator_required
def submit_mediation_outcome(request, pk):
    mediator = get_object_or_404(Mediator, user=request.user)
    session = get_object_or_404(
        MediationSession,
        pk=pk,
        mediator=mediator,
    )
    dispute = session.dispute

    if request.method == "POST":
        form = MediationOutcomeForm(request.POST, request.FILES, instance=session)
        if form.is_valid():
            form.save()
            arbitration = form.cleaned_data.get("arbitration") or False

            if arbitration:
                dispute.status = "arbitration"
                status_label = "Referred to arbitration"
            else:
                dispute.status = "mediated"
                status_label = "Mediation completed"
            dispute.save(update_fields=["status"])

            AuditLog.objects.create(
                dispute=dispute,
                user=request.user,
                action=status_label,
            )

            outcome_url = request.build_absolute_uri(
                reverse("disputes:view_outcome", args=[str(dispute.applicant_view_token)])
            )
            msg = (
                f"The mediation for your dispute has been completed. "
                f"Status: {status_label}. View outcome: {outcome_url}"
            )
            if dispute.applicant_cell:
                _send_notification(notify_recipient, to=dispute.applicant_cell, body=msg)
            respondent_cell = dispute.respondent_cell or dispute.business_cell
            if respondent_cell:
                _send_notification(notify_recipient, to=respondent_cell, body=msg)

            messages.success(request, "Outcome submitted successfully.")
            return redirect("dashboard:mediator_home")
    else:
        form = MediationOutcomeForm(instance=session)

    return render(
        request,
        "dashboard/submit_outcome.html",
        {
            "form": form,
            "session": session,
            "dispute": dispute,
        },
    )


@staff_member_required
def test_notification(request):
    """Test page for sending notifications."""
    if request.method == "POST":
        phone = request.POST.get("phone", "").strip()
        message = request.POST.get("message", "").strip()
        
        if phone and message:
            try:
                notify_recipient.delay(to=phone, body=message)
                messages.success(request, f"Notification queued for {phone}")
            except Exception as e:
                messages.error(request, f"Error: {e}")
        else:
            messages.error(request, "Please provide both phone and message")
        
        return redirect("dashboard:test_notification")
    
    from django.conf import settings
    twilio_configured = bool(
        settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN
    )
    return render(request, "dashboard/test_notification.html", {
        "debug_mode": settings.DEBUG,
        "twilio_configured": twilio_configured,
    })


@staff_member_required
def download_case_file(request, pk):
    """Download all case documents as a ZIP file for arbitration."""
    dispute = get_object_or_404(Dispute, pk=pk)
    
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        case_data = {
            "dispute_id": dispute.id,
            "applicant": {
                "name": dispute.applicant_name,
                "surname": dispute.applicant_surname,
                "cell": dispute.applicant_cell,
                "email": dispute.applicant_email,
            },
            "respondent": {
                "type": dispute.respondent_type,
                "name": dispute.respondent_name,
                "surname": dispute.respondent_surname,
                "cell": dispute.respondent_cell,
                "business_name": dispute.business_name,
                "owner_name": dispute.owner_name,
                "owner_surname": dispute.owner_surname,
                "business_cell": dispute.business_cell,
                "email": dispute.respondent_email,
            },
            "dispute_type": dispute.dispute_type,
            "description": dispute.description,
            "status": dispute.status,
            "created_at": str(dispute.created_at),
        }
        
        if hasattr(dispute, 'response'):
            case_data["respondent_response"] = {
                "consent_to_mediate": dispute.response.consent_to_mediate,
                "agreed_to_rules": dispute.response.agreed_to_rules,
                "defence_explanation": dispute.response.defence_explanation,
                "created_at": str(dispute.response.created_at),
            }
        
        if hasattr(dispute, 'mediation'):
            case_data["mediation"] = {
                "mediator": str(dispute.mediation.mediator) if dispute.mediation.mediator else None,
                "scheduled_at": str(dispute.mediation.scheduled_at),
                "zoom_link": dispute.mediation.zoom_link,
                "outcome": dispute.mediation.outcome,
            }
        
        zf.writestr('case_info.json', json.dumps(case_data, indent=2))
        
        for doc in dispute.documents.all():
            if doc.file:
                zf.writestr(f'applicant_docs/{doc.file.name}', doc.file.read())
        
        if hasattr(dispute, 'response'):
            for doc in dispute.response.documents.all():
                if doc.file:
                    zf.writestr(f'respondent_docs/{doc.file.name}', doc.file.read())
        
        if hasattr(dispute, 'mediation'):
            if dispute.mediation.outcome_file:
                zf.writestr('mediation/outcome.txt', dispute.mediation.outcome)
            if dispute.mediation.outcome_file and dispute.mediation.outcome_file.name:
                try:
                    zf.writestr('mediation/outcome_file', dispute.mediation.outcome_file.read())
                except:
                    pass
            if dispute.mediation.arbitration_agreement:
                try:
                    zf.writestr('mediation/arbitration_agreement', dispute.mediation.arbitration_agreement.read())
                except:
                    pass
            if dispute.mediation.pre_arbitration_minute:
                try:
                    zf.writestr('mediation/pre_arbitration_minute', dispute.mediation.pre_arbitration_minute.read())
                except:
                    pass
    
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename=case_{dispute.id}_arbitration.zip'
    return response


@login_required
@mediator_required
def mediator_sessions(request):
    mediator = request.user.mediator
    sessions = MediationSession.objects.filter(mediator=mediator).order_by('-scheduled_at')
    return render(request, 'dashboard/mediator_sessions.html', {'sessions': sessions})


@staff_member_required
def referred_cases_view(request):
    referred = ReferredCase.objects.select_related('dispute', 'referred_by').order_by('-referred_at')
    stats = {}
    for ref in referred:
        ref_type = ref.referred_to
        stats[ref_type] = stats.get(ref_type, 0) + 1
    return render(request, 'dashboard/referred_cases.html', {
        'referred_cases': referred,
        'page_title': 'Referred Cases',
        'referral_stats': stats
    })


@staff_member_required
def mediatable_cases_view(request):
    mediatable = MediatableCase.objects.select_related('dispute', 'accepted_by').order_by('-accepted_at')
    forwarded_count = sum(1 for c in mediatable if c.dispute.status == 'forwarded')
    responded_count = sum(1 for c in mediatable if c.dispute.status == 'responded')
    scheduled_count = sum(1 for c in mediatable if c.dispute.status == 'mediation_scheduled')
    return render(request, 'dashboard/mediatable_cases.html', {
        'mediatable_cases': mediatable,
        'page_title': 'Mediatable Cases',
        'forwarded_count': forwarded_count,
        'responded_count': responded_count,
        'scheduled_count': scheduled_count
    })


@mediator_required
@require_POST
def mediator_accept_case(request, dispute_id):
    """Mediator accepts a case - notifies applicant to confirm details"""
    try:
        dispute = Dispute.objects.get(id=dispute_id, status='responded')
    except Dispute.DoesNotExist:
        messages.error(request, "Dispute not found.")
        return redirect("dashboard:mediator_sessions")
    
    mediator = request.user.mediator
    
    # Update dispute status
    dispute.mediator = mediator
    dispute.mediator_accepted_at = timezone.now()
    dispute.status = "mediator_assigned"
    dispute.save()
    
    # Send email to applicant
    if dispute.applicant_email:
        from django.core.mail import send_mail
        from django.conf import settings
        from django.urls import reverse
        
        confirm_link = request.build_absolute_uri(
            reverse("disputes:applicant_confirm", args=[str(dispute.applicant_view_token)])
        )
        
        subject = f"Action Required: Confirm your Mediation details for Case #{dispute.id}"
        body = f"""Dear {dispute.applicant_name} {dispute.applicant_surname},

Great news! A mediator has accepted your case and will be handling your mediation.

MEDIATION DETAILS:
- Case ID: {dispute.id}
- Your Issue: {dispute.description[:200]}...
- Dispute Type: {dispute.get_dispute_type_display()}

NEXT STEPS:
Please review your information above and confirm that it is correct by clicking the link below:
{confirm_link}

If you need to amend any details or add more information, you can do so through the same link.

IMPORTANT: You must confirm your details to proceed with the mediation.

If you have any questions, please contact us.

Best regards,
Mediators on Call Team
"""
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [dispute.applicant_email])
        except Exception as e:
            logging.error(f"Failed to send applicant confirmation email: {e}")
    
    AuditLog.objects.create(
        dispute=dispute,
        user=request.user,
        action=f"Case accepted by mediator {mediator.user.get_full_name()}",
    )
    
    messages.success(request, f"Case #{dispute_id} accepted. Applicant has been notified to confirm details.")
    return redirect("dashboard:mediator_sessions")
