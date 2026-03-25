from datetime import timedelta
import logging

from django.shortcuts import (
    render,
    redirect,
    get_object_or_404,
)
from django.contrib import messages
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import (
    DisputeForm,
    DisputeDocumentFormSet,
    RespondentResponseForm,
    ResponseDocumentFormSet,
)
from .models import Dispute, DisputeDocument, DisputePhoto, TempDisputePhoto, RespondentResponse, AuditLog
from .tasks import (
    send_message_1_dispute_registered,
    send_message_4_respondent_invitation,
    send_message_5_respondent_declined,
    send_message_6_respondent_agreed,
    send_message_7_assign_mediator,
)


@require_POST
def upload_photo_ajax(request):
    """Handle AJAX photo upload - saves photos temporarily and returns success"""
    from django.http import JsonResponse
    import logging
    import traceback
    
    logger = logging.getLogger(__name__)
    
    try:
        # Handle both single file and multiple files
        files = request.FILES.getlist('photo')
        
        logger.info(f"Upload photo request: {len(files) if files else 0} files")
        
        if not files:
            return JsonResponse({'success': False, 'error': 'No photos provided'}, status=400)
        
        # Check if Pillow is available
        try:
            from PIL import Image
        except ImportError:
            return JsonResponse({'success': False, 'error': 'Image upload is temporarily unavailable.'}, status=503)
        
        uploaded_photos = []
        
        for photo in files:
            logger.info(f"Processing file: {photo.name}, size: {photo.size}, type: {photo.content_type}")
            
            # Validate file type - check both content_type and file extension
            is_image = False
            if photo.content_type and photo.content_type.startswith('image/'):
                is_image = True
            elif photo.name:
                ext = photo.name.lower().split('.')[-1] if '.' in photo.name else ''
                if ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']:
                    is_image = True
            
            if not is_image:
                return JsonResponse({'success': False, 'error': f'File {photo.name} is not an image.'}, status=400)
            
            # Validate file size (max 10MB)
            if photo.size > 10 * 1024 * 1024:
                return JsonResponse({'success': False, 'error': f'File {photo.name} is too large. Max 10MB.'}, status=400)
            
            # Get or create session key for temporary storage
            if not request.session.session_key:
                request.session.cycle_key()
            session_key = request.session.session_key
            
            logger.info(f"Session key: {session_key}")
            
            # Save temporary photo
            try:
                temp_photo = TempDisputePhoto.objects.create(
                    session_key=session_key,
                    image=photo
                )
                
                logger.info(f"Saved photo: {temp_photo.id}, url: {temp_photo.image.url}")
                
                uploaded_photos.append({
                    'id': temp_photo.id,
                    'photo_url': temp_photo.image.url
                })
            except Exception as e:
                logger.error(f"Error saving photo {photo.name}: {e}")
                logger.error(traceback.format_exc())
                return JsonResponse({'success': False, 'error': f'Failed to save image: {str(e)}'}, status=500)
        
        # Get updated count for this session
        session_key = request.session.session_key
        photo_count = TempDisputePhoto.objects.filter(session_key=session_key).count() if session_key else 0
        
        return JsonResponse({
            'success': True,
            'photos': uploaded_photos,
            'total_count': photo_count,
            'message': f'{len(uploaded_photos)} photo(s) uploaded successfully'
        })
    except Exception as e:
        logger.error(f"Unexpected error in upload_photo_ajax: {e}")
        logger.error(traceback.format_exc())
        return JsonResponse({'success': False, 'error': f'An unexpected error occurred: {str(e)}'}, status=500)


@require_POST
def remove_photo_ajax(request):
    """Remove a temporarily uploaded photo"""
    from django.http import JsonResponse
    
    photo_id = request.POST.get('photo_id')
    if not photo_id:
        return JsonResponse({'success': False, 'error': 'No photo ID provided'}, status=400)
    
    try:
        temp_photo = TempDisputePhoto.objects.get(id=photo_id)
        # Verify session matches
        if temp_photo.session_key == request.session.session_key:
            temp_photo.delete()
            return JsonResponse({'success': True, 'message': 'Photo removed'})
        else:
            return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    except TempDisputePhoto.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Photo not found'}, status=404)


def get_photos_ajax(request):
    """Get list of temporarily uploaded photos"""
    from django.http import JsonResponse
    
    session_key = request.session.session_key
    if not session_key:
        return JsonResponse({'photos': []})
    
    photos = TempDisputePhoto.objects.filter(session_key=session_key)
    photo_list = [
        {
            'id': p.id,
            'photo_url': p.image.url
        }
        for p in photos
    ]
    return JsonResponse({'photos': photo_list})


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
    from django.db import OperationalError, IntegrityError
    
    if request.method == "POST":
        form = DisputeForm(request.POST, request.FILES)
        formset = DisputeDocumentFormSet(
            request.POST, request.FILES, queryset=DisputeDocument.objects.none()
        )
        if form.is_valid() and formset.is_valid():
            try:
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
                
                # Link temporary photos to the dispute
                session_key = request.session.session_key
                if session_key:
                    try:
                        temp_photos = TempDisputePhoto.objects.filter(session_key=session_key)
                        for temp_photo in temp_photos:
                            try:
                                DisputePhoto.objects.create(
                                    dispute=dispute,
                                    image=temp_photo.image
                                )
                            except Exception as e:
                                logging.warning(f"Could not save photo: {e}")
                        # Clean up temp photos
                        temp_photos.delete()
                    except Exception as e:
                        logging.warning(f"Error linking photos: {e}")
                
                # Send Message 1: Thank you for submitting dispute confirmation
                if dispute.applicant_email:
                    try:
                        send_message_1_dispute_registered.delay(
                            to_email=dispute.applicant_email,
                            applicant_name=dispute.applicant_name,
                            case_id=dispute.id,
                        )
                    except Exception:
                        pass
                
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
                
                messages.success(request, "Your dispute has been submitted successfully. You will receive an SMS notification shortly.")
                return redirect("disputes:application_success")
                
            except (OperationalError, IntegrityError) as e:
                logging.error(f"Database error submitting dispute: {e}")
                messages.error(request, "There was a temporary problem saving your dispute. Please try again in a moment. If the problem persists, contact us directly.")
                return render(request, "disputes/apply.html", {"form": form, "formset": formset})
        else:
            # Form is invalid - render with errors
            return render(request, "disputes/apply.html", {"form": form, "formset": formset})
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

            # Handle mutual agreement workflow
            if form.cleaned_data["consent_to_mediate"]:
                # Respondent agreed - notify applicant for final confirmation
                dispute.status = "respondent_agreed"
                dispute.respondent_agreed_at = timezone.now()
                dispute.save(update_fields=["status", "respondent_agreed_at"])
                
                # Send Message 6: Respondent agreed to applicant
                if dispute.applicant_email:
                    final_confirm_link = request.build_absolute_uri(
                        reverse("disputes:applicant_final_confirm", args=[str(dispute.applicant_view_token)])
                    )
                    send_message_6_respondent_agreed.delay(
                        to_email=dispute.applicant_email,
                        applicant_name=dispute.applicant_name,
                        final_confirm_link=final_confirm_link,
                        case_id=dispute.id,
                    )
                
                AuditLog.objects.create(
                    dispute=dispute,
                    user=None,
                    action="Respondent agreed - Applicant notified for final confirmation",
                )
                
                return render(request, "disputes/respond_agreed.html", {"dispute": dispute})
            else:
                dispute.status = "responded"
                dispute.save(update_fields=["status"])
                
                # Send Message 5: Respondent declined
                if dispute.applicant_email:
                    send_message_5_respondent_declined.delay(
                        to_email=dispute.applicant_email,
                        applicant_name=dispute.applicant_name,
                        case_id=dispute.id,
                    )

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


def applicant_confirm_view(request, token):
    """Applicant confirms their details after mediator accepts case"""
    dispute = get_object_or_404(Dispute, applicant_view_token=token)
    
    if dispute.status not in ['mediator_assigned']:
        messages.error(request, "This case is not awaiting confirmation.")
        return redirect("disputes:apply")
    
    if request.method == "POST":
        amended_details = request.POST.get("amended_details", "")
        
        # Update dispute
        dispute.applicant_confirmed_at = timezone.now()
        dispute.applicant_amended_details = amended_details
        dispute.status = "applicant_confirmed"
        dispute.save()
        
        # Notify respondent
        from django.core.mail import send_mail
        from django.conf import settings
        from datetime import timedelta
        
        # Set 7-day deadline
        dispute.respondent_notified_at = timezone.now()
        dispute.respondent_response_deadline = timezone.now() + timedelta(days=7)
        dispute.save()
        
        # Send notification to respondent
        if dispute.respondent_email:
            respond_link = request.build_absolute_uri(
                reverse("disputes:respond", args=[str(dispute.respondent_token)])
            )
            
            subject = f"Mediation Request - You have 7 days to respond - Case #{dispute.id}"
            body = f"""Dear Respondent,

A mediation case has been opened regarding your dispute with {dispute.applicant_name} {dispute.applicant_surname}.

CASE DETAILS:
- Case ID: {dispute.id}
- Applicant: {dispute.applicant_name} {dispute.applicant_surname}
- Issue: {dispute.description[:200]}...

You have 7 DAYS to respond to this mediation request.

To respond, please click the link below:
{respond_link}

If you do not respond within 7 days, a reminder will be sent. If you still don't respond after 14 days, the case may be closed.

To view the full case details and respond, please use the link above.

Best regards,
Mediators on Call Team
"""
            try:
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [dispute.respondent_email])
            except Exception as e:
                logging.error(f"Failed to send respondent email: {e}")
        
        # Send SMS to respondent
        if dispute.respondent_cell:
            from disputes.tasks import notify_recipient
            sms_body = f"Mediation case #{dispute.id}. You have 7 days to respond. Please check your email for details."
            try:
                notify_recipient.delay(to=dispute.respondent_cell, body=sms_body)
            except:
                pass
        
        return render(request, "disputes/confirm_success.html", {"dispute": dispute})
    
    return render(request, "disputes/applicant_confirm.html", {"dispute": dispute})


def applicant_final_confirm_view(request, token):
    """Applicant gives final confirmation after respondent agrees"""
    dispute = get_object_or_404(Dispute, applicant_view_token=token)
    
    if dispute.status not in ['respondent_agreed']:
        messages.error(request, "This case is not awaiting final confirmation.")
        return redirect("disputes:apply")
    
    response = getattr(dispute, "response", None)
    
    if request.method == "POST":
        # Update dispute status
        dispute.applicant_final_confirmed_at = timezone.now()
        dispute.status = "ready_for_assignment"
        dispute.save(update_fields=["applicant_final_confirmed_at", "status"])
        
        # Send Message 7: Notify admin to assign mediator
        from django.conf import settings
        admin_email = getattr(settings, 'ADMIN_EMAIL', 'admin@probonomediation.co.za')
        send_message_7_assign_mediator.delay(
            admin_email=admin_email,
            case_id=dispute.id,
        )
        
        AuditLog.objects.create(
            dispute=dispute,
            user=None,
            action="Applicant gave final confirmation - Case ready for mediator assignment",
        )
        
        return render(request, "disputes/final_confirm_success.html", {"dispute": dispute})
    
    return render(request, "disputes/applicant_final_confirm.html", {"dispute": dispute, "response": response})
