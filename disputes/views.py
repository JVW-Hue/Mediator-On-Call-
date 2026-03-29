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


def get_session_key(request):
    """Get session key using IP-based identifier - no Django sessions needed"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', 'unknown')
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:200]
    return f"{ip}_{hash(user_agent) % 100000}"


def get_temp_photo_dir(session_key):
    """Get directory for temp photos based on session key"""
    import os
    from django.conf import settings
    safe_key = session_key.replace('.', '_').replace(':', '_')
    photo_dir = os.path.join(settings.MEDIA_ROOT, 'temp_photos', safe_key)
    os.makedirs(photo_dir, exist_ok=True)
    return photo_dir


@require_POST
def upload_photo_ajax(request):
    """Handle AJAX photo upload - saves photos directly to filesystem"""
    from django.http import JsonResponse
    from django.conf import settings
    import logging
    import traceback
    import os
    import uuid
    
    logger = logging.getLogger(__name__)
    
    try:
        files = request.FILES.getlist('photo')
        logger.info(f"Upload photo request: {len(files) if files else 0} files")
        
        if not files:
            return JsonResponse({'success': False, 'error': 'No photos provided'}, status=400)
        
        uploaded_photos = []
        session_key = get_session_key(request)
        photo_dir = get_temp_photo_dir(session_key)
        
        for photo in files:
            logger.info(f"Processing file: {photo.name}, size: {photo.size}")
            
            # Validate file type
            ext = photo.name.lower().split('.')[-1] if '.' in photo.name else 'jpg'
            if ext not in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']:
                ext = 'jpg'
            
            # Validate file size (max 10MB)
            if photo.size > 10 * 1024 * 1024:
                return JsonResponse({'success': False, 'error': f'File {photo.name} is too large. Max 10MB.'}, status=400)
            
            # Generate unique filename
            unique_name = f"{uuid.uuid4().hex}.{ext}"
            file_path = os.path.join(photo_dir, unique_name)
            
            # Save file directly
            with open(file_path, 'wb') as f:
                for chunk in photo.chunks():
                    f.write(chunk)
            
            # Build URL
            relative_path = f"temp_photos/{session_key}/{unique_name}"
            photo_url = f"{settings.MEDIA_URL}{relative_path}"
            
            logger.info(f"Saved photo: {file_path}, url: {photo_url}")
            
            uploaded_photos.append({
                'id': unique_name,
                'photo_url': photo_url,
                'filename': photo.name
            })
        
        return JsonResponse({
            'success': True,
            'photos': uploaded_photos,
            'total_count': len(uploaded_photos),
            'message': f'{len(uploaded_photos)} photo(s) uploaded successfully'
        })
    except Exception as e:
        logger.error(f"Error in upload_photo_ajax: {e}")
        logger.error(traceback.format_exc())
        return JsonResponse({'success': False, 'error': f'Failed to save image: {str(e)}'}, status=500)


@require_POST
def remove_photo_ajax(request):
    """Remove a temporarily uploaded photo"""
    from django.http import JsonResponse
    from django.conf import settings
    import os
    
    photo_id = request.POST.get('photo_id')
    if not photo_id:
        return JsonResponse({'success': False, 'error': 'No photo ID provided'}, status=400)
    
    session_key = get_session_key(request)
    safe_key = session_key.replace('.', '_').replace(':', '_')
    file_path = os.path.join(settings.MEDIA_ROOT, 'temp_photos', safe_key, photo_id)
    
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return JsonResponse({'success': True, 'message': 'Photo removed'})
        else:
            return JsonResponse({'success': False, 'error': 'Photo not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def get_photos_ajax(request):
    """Get list of temporarily uploaded photos"""
    from django.http import JsonResponse
    from django.conf import settings
    import os
    
    session_key = get_session_key(request)
    safe_key = session_key.replace('.', '_').replace(':', '_')
    photo_dir = os.path.join(settings.MEDIA_ROOT, 'temp_photos', safe_key)
    
    photo_list = []
    if os.path.exists(photo_dir):
        for filename in os.listdir(photo_dir):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
                photo_list.append({
                    'id': filename,
                    'photo_url': f"{settings.MEDIA_URL}temp_photos/{safe_key}/{filename}"
                })
    
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
    from django.db import OperationalError, IntegrityError, connection
    
    if request.method == "POST":
        form = DisputeForm(request.POST, request.FILES)
        formset = DisputeDocumentFormSet(
            request.POST, request.FILES, queryset=DisputeDocument.objects.none()
        )
        
        # Debug: log form errors
        if not form.is_valid():
            logging.error(f"Form errors: {form.errors}")
        if not formset.is_valid():
            logging.error(f"Formset errors: {formset.errors}")
        
        if form.is_valid() and formset.is_valid():
            try:
                # Check database connection
                try:
                    connection.ensure_connection()
                except Exception as db_err:
                    logging.error(f"Database connection error: {db_err}")
                    messages.error(request, "Database connection error. Please try again.")
                    return render(request, "disputes/apply.html", {"form": form, "formset": formset})
                
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
                
                # Verify save
                if dispute.id:
                    logging.info(f"Dispute saved successfully with ID: {dispute.id}")
                else:
                    logging.error("Dispute save returned no ID!")
                    messages.error(request, "Error saving dispute. Please try again.")
                    return render(request, "disputes/apply.html", {"form": form, "formset": formset})
                
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
                session_key = get_session_key(request)
                if session_key:
                    try:
                        import os
                        from django.conf import settings
                        safe_key = session_key.replace('.', '_').replace(':', '_')
                        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_photos', safe_key)
                        
                        if os.path.exists(temp_dir):
                            for filename in os.listdir(temp_dir):
                                if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
                                    try:
                                        temp_path = os.path.join(temp_dir, filename)
                                        # Create DisputePhoto with file
                                        with open(temp_path, 'rb') as f:
                                            from django.core.files.base import ContentFile
                                            photo_content = ContentFile(f.read())
                                            dispute_photo = DisputePhoto(dispute=dispute)
                                            dispute_photo.image.save(filename, photo_content)
                                            dispute_photo.save()
                                    except Exception as e:
                                        logging.warning(f"Could not save photo: {e}")
                            
                            # Clean up temp directory
                            import shutil
                            shutil.rmtree(temp_dir, ignore_errors=True)
                    except Exception as e:
                        logging.warning(f"Error linking photos: {e}")
                
                # Send Message 1: Thank you for submitting dispute confirmation (Email + SMS)
                try:
                    send_message_1_dispute_registered.delay(
                        to_email=dispute.applicant_email or '',
                        applicant_name=dispute.applicant_name,
                        case_id=dispute.id,
                        to_phone=dispute.applicant_cell or None,
                    )
                except Exception as e:
                    logging.warning(f"Could not send confirmation: {e}")
                
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
            except Exception as e:
                logging.error(f"Error submitting dispute: {type(e).__name__}: {e}")
                import traceback
                logging.error(traceback.format_exc())
                messages.error(request, f"Error: {type(e).__name__}. Please try again or contact support.")
                return render(request, "disputes/apply.html", {"form": form, "formset": formset})
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


def setup_admin_view(request):
    """Setup mediator accounts - access at /setup-admin/"""
    from django.contrib.auth import get_user_model
    from .models import Mediator
    from django.http import HttpResponse
    
    User = get_user_model()
    
    try:
        # Delete existing frankstanley
        User.objects.filter(username='frankstanley').delete()
        
        # Create Frank Stanley as MEDIATOR only (not superuser)
        # But with staff access so he can see all cases and assign mediators
        user = User.objects.create_user(
            username='frankstanley',
            email='frank@probonomediation.co.za',
            password='FrankStanley2026!'
        )
        user.first_name = 'Frank'
        user.last_name = 'Stanley'
        user.is_staff = True  # Can access dashboard
        user.is_superuser = False  # NOT a superuser
        user.is_active = True
        user.save()
        
        # Create mediator profile - this makes him a mediator
        mediator, created = Mediator.objects.get_or_create(
            user=user, 
            defaults={'cell': '0821234567'}
        )
        
        # Create JVW mediator
        User.objects.filter(username='JVW').delete()
        jvw = User.objects.create_user(
            username='JVW',
            email='jvw@probonomediation.co.za',
            password='JVW123'
        )
        jvw.is_staff = True
        jvw.is_active = True
        jvw.save()
        Mediator.objects.get_or_create(user=jvw, defaults={'cell': '0000000000'})
        
        return HttpResponse("""
        <html>
        <head><title>Mediator Accounts Created</title>
        <style>
            body { font-family: Arial; padding: 40px; background: #f0f0f0; }
            .box { background: white; padding: 30px; border-radius: 10px; max-width: 500px; margin: 0 auto; }
            .success { color: green; font-weight: bold; }
            table { width: 100%; border-collapse: collapse; margin: 20px 0; }
            td { padding: 10px; border-bottom: 1px solid #eee; }
            td:first-child { font-weight: bold; width: 150px; }
        </style>
        </head>
        <body>
        <div class="box">
            <h1 class="success">Mediator Accounts Created!</h1>
            
            <h2>Frank Stanley (Lead Mediator)</h2>
            <p>Can see ALL cases and assign mediators</p>
            <table>
                <tr><td>Username:</td><td>frankstanley</td></tr>
                <tr><td>Password:</td><td>FrankStanley2026!</td></tr>
                <tr><td>Email:</td><td>frank@probonomediation.co.za</td></tr>
                <tr><td>Role:</td><td>Mediator (can assign cases)</td></tr>
            </table>
            
            <h2>JVW (Mediator)</h2>
            <table>
                <tr><td>Username:</td><td>JVW</td></tr>
                <tr><td>Password:</td><td>JVW123</td></tr>
            </table>
            
            <p><a href="/dashboard/">Login to Dashboard</a></p>
        </div>
        </body>
        </html>
        """)
        
    except Exception as e:
        return HttpResponse(f"<h1>Error: {e}</h1><p>Check Render logs for details.</p>")
