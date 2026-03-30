from datetime import datetime, timedelta
import io
import json
import zipfile
import logging
from functools import wraps

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django import forms
from django.core.exceptions import PermissionDenied
from django.db import models, OperationalError
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView

from disputes.models import Dispute, MediationSession, Mediator, AuditLog, MediatableCase, ReferredCase
from disputes.tasks import notify_recipient, send_message_2_dispute_rejected, send_message_3_proceed_mediation, send_message_4_respondent_invitation, send_message_8_mediator_assigned_mediator, send_message_8_mediator_assigned_parties, send_message_9_outcome_filed
from disputes.forms import MediationOutcomeForm


def staff_required(view_func):
    """Custom staff decorator that uses our login page."""
    @wraps(view_func)
    @login_required(login_url='/login/')
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('/no-access/')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


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
            return redirect('/login/')
        if not hasattr(request.user, 'mediator') and not request.user.is_staff:
            return redirect('no_access')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


class CustomLoginView(auth_views.LoginView):
    template_name = 'registration/login.html'
    
    @staticmethod
    def ensure_frankstanley_exists():
        """Ensure Frank Stanley account exists - called on every login attempt."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user, created = User.objects.get_or_create(
                username='frankstanley',
                defaults={
                    'email': 'frank@probonomediation.co.za',
                    'first_name': 'Frank',
                    'last_name': 'Stanley',
                    'is_staff': True,
                    'is_superuser': False,
                    'is_active': True,
                }
            )
            if created:
                user.set_password('FrankStanley2026!')
                user.save()
            from disputes.models import Mediator
            Mediator.objects.get_or_create(user=user, defaults={'cell': '0821234567'})
        except Exception as e:
            logging.error(f"Error ensuring frankstanley exists: {e}")
    
    def post(self, request, *args, **kwargs):
        self.ensure_frankstanley_exists()
        return super().post(request, *args, **kwargs)
    
    def form_valid(self, form):
        try:
            remember_me = self.request.POST.get('remember_me')
            if remember_me:
                self.request.session.set_expiry(60 * 60 * 24 * 30)  # 30 days
            else:
                self.request.session.set_expiry(0)  # Session expires when browser closes
            response = super().form_valid(form)
            return response
        except Exception as e:
            logging.error(f"Error during login form_valid: {e}")
            messages.error(self.request, "There was a temporary problem logging in. Please try again.")
            return self.form_invalid(form)

    def get_success_url(self):
        try:
            user = self.request.user
            # Staff OR has mediator profile can access dashboard
            if user.is_staff or user.is_superuser:
                return '/dashboard/'
            try:
                mediator = Mediator.objects.get(user=user)
                return '/dashboard/mediator/'
            except Mediator.DoesNotExist:
                return '/no-access/'
        except Exception as e:
            logging.error(f"Error during get_success_url: {e}")
            return '/dashboard/'
    
    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

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
    from django.db import OperationalError
    from django.contrib import messages
    from django.contrib.auth import authenticate, login
    
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
            try:
                if User.objects.filter(username=username).exists():
                    raise forms.ValidationError("Username already exists")
            except OperationalError:
                # If the database table doesn't exist yet, we can't check for duplicates
                # In this case, we'll allow the username to pass validation
                # The user will be informed later if there's an issue
                pass
            return username
        
        def clean(self):
            cleaned_data = super().clean()
            try:
                if cleaned_data.get('password1') != cleaned_data.get('password2'):
                    raise forms.ValidationError("Passwords do not match")
            except OperationalError:
                # If there's a database error during validation, we'll still check the passwords
                # This is a fallback in case of migration issues
                if cleaned_data.get('password1') != cleaned_data.get('password2'):
                    raise forms.ValidationError("Passwords do not match")
            return cleaned_data
    
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            try:
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
                
                user = authenticate(username=form.cleaned_data['username'], password=form.cleaned_data['password1'])
                if user:
                    login(request, user)
                    if user.is_staff:
                        return redirect('dashboard:admin_home')
                    else:
                        return redirect('dashboard:mediator_home')
                else:
                    messages.error(request, "Authentication failed after user creation.")
                    return render(request, 'registration/signup.html', {'form': form})
            except OperationalError as e:
                messages.error(request, "There was a temporary database error. Please try again in a moment. If the problem persists, please contact the administrator.")
                return render(request, 'registration/signup.html', {'form': form})
            except Exception as e:
                messages.error(request, "An unexpected error occurred during registration. Please try again.")
                return render(request, 'registration/signup.html', {'form': form})
    else:
        form = SignupForm()
    return render(request, 'registration/signup.html', {'form': form})


@method_decorator(staff_required, name="dispatch")
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
        
        calendar_events = [
            {
                "title": f"Dispute #{s.dispute.id} - {s.mediator.user.get_full_name() or s.mediator.user.username}",
                "start": s.scheduled_at.isoformat(),
                "url": reverse("dashboard:dispute_detail", args=[s.dispute.id]),
                "backgroundColor": "#198754" if s.dispute.status == "mediation_scheduled" else "#0d6efd",
            }
            for s in sessions
        ]
        
        # Add calendar notes
        from disputes.models import CalendarNote
        notes = CalendarNote.objects.filter(
            date__gte=timezone.now().date() - timedelta(days=365)
        ).select_related("user")
        for note in notes:
            calendar_events.append({
                "title": f"Note: {note.note[:40]}{'...' if len(note.note) > 40 else ''}",
                "start": note.date.isoformat(),
                "backgroundColor": "#6c757d",
                "borderColor": "#6c757d",
            })
        
        context["calendar_events"] = calendar_events
        return context


@method_decorator(staff_required, name="dispatch")
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


@staff_required
def delete_dispute(request, pk):
    dispute = get_object_or_404(Dispute, pk=pk)
    dispute.delete()
    messages.success(request, f"Dispute #{pk} deleted successfully.")
    return redirect("dashboard:dispute_list")


@method_decorator(staff_required, name="dispatch")
class DisputeDetailView(DetailView):
    model = Dispute
    template_name = "dashboard/dispute_detail.html"
    context_object_name = "dispute"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["mediators"] = Mediator.objects.select_related("user").all()
        return context


@staff_required
@require_POST
def assign_mediator_to_dispute(request, pk):
    """Assign mediator directly from dispute detail page."""
    dispute = get_object_or_404(Dispute, pk=pk)
    mediator_id = request.POST.get("mediator_id")
    scheduled_at_str = request.POST.get("scheduled_at")
    zoom_link = request.POST.get("zoom_link", "https://zoom.us/j/pending")
    
    if not mediator_id:
        messages.error(request, "Please select a mediator.")
        return redirect("dashboard:dispute_detail", pk=pk)
    
    mediator = get_object_or_404(Mediator, id=mediator_id)
    
    try:
        scheduled_at = datetime.fromisoformat(scheduled_at_str)
    except (ValueError, AttributeError):
        messages.error(request, "Invalid date/time format.")
        return redirect("dashboard:dispute_detail", pk=pk)
    
    if timezone.is_naive(scheduled_at):
        scheduled_at = timezone.make_aware(scheduled_at, timezone.utc)
    
    # Create or update mediation session
    session, created = MediationSession.objects.update_or_create(
        dispute=dispute,
        defaults={
            "mediator": mediator,
            "scheduled_at": scheduled_at,
            "zoom_link": zoom_link,
            "host_link": "",
        }
    )
    
    # Update dispute
    dispute.mediator = mediator
    dispute.status = "mediation_scheduled"
    dispute.save()
    
    mediator_name = mediator.user.get_full_name() or mediator.user.username
    mediator_email = mediator.user.email
    
    # Send Message 8: Notify mediator
    if mediator_email:
        try:
            send_message_8_mediator_assigned_mediator.delay(
                to_email=mediator_email,
                mediator_name=mediator_name,
                case_id=dispute.id,
            )
        except Exception:
            pass
    
    # Send Message 8: Notify parties
    try:
        send_message_8_mediator_assigned_parties.delay(
            applicant_email=dispute.applicant_email,
            respondent_email=dispute.respondent_email,
            mediator_name=mediator_name,
            case_id=dispute.id,
        )
    except Exception:
        pass
    
    # SMS notification to mediator
    if mediator.cell:
        try:
            notify_recipient.delay(
                to=mediator.cell,
                body=f"You have been assigned to Dispute #{dispute.id}. Applicant: {dispute.applicant_name} {dispute.applicant_surname}. Session: {scheduled_at.strftime('%d %b %Y %H:%M')}."
            )
        except Exception:
            pass
    
    AuditLog.objects.create(
        dispute=dispute,
        user=request.user,
        action=f"Mediator {mediator_name} assigned, session scheduled for {scheduled_at}",
    )

    messages.success(request, f"Mediator {mediator_name} assigned to Dispute #{pk}!")
    return redirect("dashboard:dispute_list")


@staff_required
@require_POST
def screen_dispute(request):
    """Process screening decision from dispute list."""
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
        respondent_name = (
            f"{dispute.respondent_name or ''} {dispute.respondent_surname or ''}".strip()
            or dispute.business_name
            or "Respondent"
        )
        
        # Send Message 4: Invitation to respondent
        respondent_email = dispute.respondent_email or dispute.business_email
        if respondent_email:
            send_message_4_respondent_invitation.delay(
                to_email=respondent_email,
                respondent_name=respondent_name,
                applicant_name=f"{dispute.applicant_name} {dispute.applicant_surname}",
                respond_link=respondent_link,
                case_id=dispute.id,
            )
        
        # Send SMS to respondent
        respondent_cell = dispute.respondent_cell or dispute.business_cell
        if respondent_cell:
            _send_notification(
                notify_recipient,
                to=respondent_cell,
                body=f"A dispute has been filed against you. Please respond here: {respondent_link}",
            )

        # Send Message 3: Proceed with mediation to applicant
        if dispute.applicant_email:
            send_message_3_proceed_mediation.delay(
                to_email=dispute.applicant_email,
                applicant_name=dispute.applicant_name,
                case_id=dispute.id,
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
        
        # Send Message 2: Dispute rejected notification
        if dispute.applicant_email:
            send_message_2_dispute_rejected.delay(
                to_email=dispute.applicant_email,
                applicant_name=dispute.applicant_name,
                case_id=dispute.id,
            )

        # Send SMS notification
        if dispute.applicant_cell:
            sms_body = (
                "After reviewing your request we have found that the dispute cannot be mediated. "
                "Your file has been closed. You are welcome to lodge an enquiry to complaints@probonomediation.co.za"
            )
            _send_notification(notify_recipient, to=dispute.applicant_cell, body=sms_body)

        AuditLog.objects.create(
            dispute=dispute,
            user=request.user,
            action=f"Dispute rejected - referred to {refer_to}" if refer_to else "Dispute rejected - not mediatable",
        )

        messages.warning(request, f"Dispute #{dispute_id} rejected and applicant notified.")

    return redirect("dashboard:dispute_list")


@staff_required
def screen_dispute_page(request, pk):
    """Show full dispute profile for screening."""
    dispute = get_object_or_404(Dispute, pk=pk, status="submitted")
    
    if request.method == "POST":
        decision = request.POST.get("decision")
        notes = request.POST.get("notes", "")
        refer_to = request.POST.get("refer_to", "")
        refer_notes = request.POST.get("refer_notes", "")
        offer_foresolve = request.POST.get("offer_foresolve") == "on"

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
            
            respondent_name = (
                f"{dispute.respondent_name or ''} {dispute.respondent_surname or ''}".strip()
                or dispute.business_name
                or "Respondent"
            )
            
            # Send Message 4: Invitation to respondent
            respondent_email = dispute.respondent_email or dispute.business_email
            if respondent_email:
                send_message_4_respondent_invitation.delay(
                    to_email=respondent_email,
                    respondent_name=respondent_name,
                    applicant_name=f"{dispute.applicant_name} {dispute.applicant_surname}",
                    respond_link=respondent_link,
                    case_id=dispute.id,
                )
            
            # Send SMS to respondent
            respondent_cell = dispute.respondent_cell or dispute.business_cell
            if respondent_cell:
                _send_notification(
                    notify_recipient,
                    to=respondent_cell,
                    body=f"A dispute has been filed against you. Please respond here: {respondent_link}",
                )

            # Send Message 3: Proceed with mediation to applicant
            if dispute.applicant_email:
                send_message_3_proceed_mediation.delay(
                    to_email=dispute.applicant_email,
                    applicant_name=dispute.applicant_name,
                    case_id=dispute.id,
                )

            if dispute.applicant_cell:
                _send_notification(
                    notify_recipient,
                    to=dispute.applicant_cell,
                    body="Your dispute has been accepted and forwarded to the respondent.",
                )

            AuditLog.objects.create(
                dispute=dispute,
                user=request.user,
                action="Dispute accepted and forwarded to respondent",
            )

            messages.success(request, f"Dispute #{dispute.id} accepted and forwarded.")
            return redirect("dashboard:dispute_list")
        else:
            dispute.is_mediatable = False
            dispute.status = "rejected"
            if refer_to:
                dispute.screening_notes = f"REFERRED TO: {refer_to.upper()}. Notes: {notes}"
            else:
                dispute.screening_notes = notes

            dispute.screened_by = request.user
            dispute.screened_at = timezone.now()
            dispute.save()

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
            
            # Send Message 2: Dispute rejected notification
            if dispute.applicant_email:
                send_message_2_dispute_rejected.delay(
                    to_email=dispute.applicant_email,
                    applicant_name=dispute.applicant_name,
                    case_id=dispute.id,
                )

            if dispute.applicant_cell:
                sms_body = "After reviewing your request we have found that the dispute cannot be mediated. Your file has been closed. You are welcome to lodge an enquiry to complaints@probonomediation.co.za"
                _send_notification(notify_recipient, to=dispute.applicant_cell, body=sms_body)

            AuditLog.objects.create(
                dispute=dispute,
                user=request.user,
                action=f"Dispute rejected - referred to {refer_to}" if refer_to else "Dispute rejected",
            )

            messages.warning(request, f"Dispute #{dispute.id} rejected.")
            return redirect("dashboard:dispute_list")
    
    return render(request, "dashboard/screen_dispute.html", {"dispute": dispute})


@staff_required
@require_POST
def assign_mediator_post(request):
    """Handle assign mediator from modal on dispute list."""
    dispute_id = request.POST.get("dispute_id")
    mediator_id = request.POST.get("mediator_id")
    scheduled_at_str = request.POST.get("scheduled_at")
    
    if not dispute_id or not mediator_id:
        messages.error(request, "Please select a mediator and date/time.")
        return redirect("dashboard:dispute_list")
    
    dispute = get_object_or_404(Dispute, pk=dispute_id, status__in=["responded", "ready_for_assignment"])
    mediator = get_object_or_404(Mediator, id=mediator_id)
    
    try:
        scheduled_at = datetime.fromisoformat(scheduled_at_str)
    except (ValueError, AttributeError):
        messages.error(request, "Invalid date/time format.")
        return redirect("dashboard:dispute_list")
    
    if timezone.is_naive(scheduled_at):
        scheduled_at = timezone.make_aware(scheduled_at, timezone.utc)
    
    session = MediationSession.objects.create(
        dispute=dispute,
        mediator=mediator,
        scheduled_at=scheduled_at,
        zoom_link="https://zoom.us/j/pending",
        host_link="",
    )
    
    dispute.status = "mediation_scheduled"
    dispute.mediator = mediator
    dispute.save()
    
    mediator_name = mediator.user.get_full_name() or mediator.user.username
    
    # Send notifications
    if mediator.user.email:
        send_message_8_mediator_assigned_mediator.delay(
            to_email=mediator.user.email,
            mediator_name=mediator_name,
            case_id=dispute.id,
        )
    
    send_message_8_mediator_assigned_parties.delay(
        applicant_email=dispute.applicant_email,
        respondent_email=dispute.respondent_email or dispute.business_email,
        mediator_name=mediator_name,
        case_id=dispute.id,
    )
    
    AuditLog.objects.create(
        dispute=dispute,
        user=request.user,
        action=f"Mediator {mediator_name} assigned via modal, session scheduled for {scheduled_at}",
    )
    
    messages.success(request, f"Mediator {mediator_name} assigned to Dispute #{dispute_id}!")
    return redirect("dashboard:dispute_list")


@staff_required
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


@staff_required
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


@login_required
@mediator_required
def mediator_sessions(request):
    """Show mediation sessions for the current user."""
    sessions = MediationSession.objects.none()  # Empty queryset by default
    
    # If user has a mediator profile, show their sessions
    if hasattr(request.user, 'mediator'):
        mediator = request.user.mediator
        sessions = MediationSession.objects.filter(mediator=mediator).order_by('-scheduled_at')
    # If user is staff, show all sessions
    elif request.user.is_staff:
        sessions = MediationSession.objects.all().order_by('-scheduled_at')
    
    return render(request, 'dashboard/mediator_sessions.html', {'sessions': sessions})


@login_required
def mediator_dashboard(request):
    """Dashboard view for mediators showing their cases and sessions."""
    mediator = None
    assigned_cases = Dispute.objects.none()
    upcoming_sessions = MediationSession.objects.none()
    
    # If user has a mediator profile, show their cases
    if hasattr(request.user, 'mediator'):
        mediator = request.user.mediator
        assigned_cases = Dispute.objects.filter(mediator=mediator).order_by('-created_at')
        upcoming_sessions = MediationSession.objects.filter(
            mediator=mediator,
            scheduled_at__gte=timezone.now()
        ).order_by('scheduled_at')
    # If user is staff, show all cases
    elif request.user.is_staff:
        assigned_cases = Dispute.objects.all().order_by('-created_at')
        upcoming_sessions = MediationSession.objects.filter(
            scheduled_at__gte=timezone.now()
        ).order_by('scheduled_at')
    
    # Calculate stats
    stats = {
        'assigned_count': assigned_cases.count(),
        'pending_count': assigned_cases.filter(status__in=['mediator_assigned', 'ready_for_assignment']).count(),
        'upcoming_count': upcoming_sessions.count(),
        'completed_count': assigned_cases.filter(status='mediated').count(),
    }
    
    # Get recently completed cases
    completed_cases = assigned_cases.filter(status='mediated').order_by('-created_at')[:5]
    
    context = {
        'mediator': mediator,
        'stats': stats,
        'upcoming': upcoming_sessions[:6],
        'assigned_cases': assigned_cases[:6],
        'completed_cases': completed_cases,
    }
    
    return render(request, 'dashboard/mediator_home.html', context)


@login_required
@mediator_required
def submit_mediation_outcome(request, pk):
    """Submit outcome for a mediation session."""
    session = get_object_or_404(MediationSession, pk=pk, mediator=request.user.mediator)
    
    if request.method == 'POST':
        outcome = request.POST.get('outcome', '')
        
        # Handle outcome file upload if provided
        outcome_file = request.FILES.get('outcome_file')
        
        session.outcome = outcome
        if outcome_file:
            session.outcome_file = outcome_file
        session.save()
        
        # Update dispute status
        dispute = session.dispute
        dispute.status = 'mediated'
        dispute.save()
        
        # Send notifications
        if dispute.applicant_email:
            try:
                send_message_9_outcome_filed.delay(
                    to_email=dispute.applicant_email,
                    applicant_name=dispute.applicant_name,
                    case_id=dispute.id,
                    outcome=outcome[:200]
                )
            except Exception:
                pass
        
        AuditLog.objects.create(
            dispute=dispute,
            user=request.user,
            action=f"Mediation outcome submitted by {request.user.get_full_name() or request.user.username}",
        )
        
        messages.success(request, f"Outcome for dispute #{dispute.id} submitted successfully.")
        return redirect('dashboard:mediator_home')
    
    context = {
        'session': session,
        'dispute': session.dispute,
    }
    return render(request, 'dashboard/submit_outcome.html', context)


def mediators_list(request):
    """List all mediators in the database."""
    # Only allow GET requests to prevent form resubmission issues
    if request.method != 'GET':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['GET'])
    
    mediators = Mediator.objects.select_related('user').all().order_by('user__first_name', 'user__last_name')
    
    # Get search query
    search = request.GET.get('search', '')
    if search:
        from django.db.models import Q
        mediators = mediators.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(user__email__icontains=search) |
            Q(cell__icontains=search)
        )
    
    # Get stats
    total_mediators = mediators.count()
    
    context = {
        'mediators': mediators,
        'total_mediators': total_mediators,
        'search_query': search,
    }
    return render(request, 'dashboard/mediators_list.html', context)


@staff_required
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


@staff_required
def assign_mediator_page(request, pk):
    """Show page for assigning mediator to a dispute."""
    dispute = get_object_or_404(Dispute, pk=pk, status__in=["responded", "ready_for_assignment"])
    mediators = Mediator.objects.select_related("user").all()
    
    if request.method == "POST":
        mediator_id = request.POST.get("mediator_id")
        scheduled_at_str = request.POST.get("scheduled_at")
        join_url = request.POST.get("join_url", "")
        host_url = request.POST.get("host_url", "")

        mediator = get_object_or_404(Mediator, id=mediator_id)

        try:
            scheduled_at = datetime.fromisoformat(scheduled_at_str)
        except (ValueError, AttributeError):
            messages.error(request, "Invalid date/time format.")
    return render(request, "dashboard/assign_mediator.html", {"dispute": dispute, "mediators": mediators})


@staff_required
@require_POST
def save_calendar_note(request):
    """Save a calendar note (AJAX endpoint)."""
    import json
    from django.http import JsonResponse
    from disputes.models import CalendarNote
    from datetime import datetime
    
    try:
        data = json.loads(request.body)
        date_str = data.get('date')
        note_text = data.get('note')
        
        if not date_str or not note_text:
            return JsonResponse({'success': False, 'error': 'Missing date or note'})
        
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        CalendarNote.objects.create(
            user=request.user,
            date=date,
            note=note_text
        )
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
        
        if timezone.is_naive(scheduled_at):
            scheduled_at = timezone.make_aware(scheduled_at, timezone.utc)

        respondent_name = (
            f"{dispute.respondent_name or ''} {dispute.respondent_surname or ''}".strip()
            or dispute.business_name
            or "Respondent"
        )

        session = MediationSession.objects.create(
            dispute=dispute,
            mediator=mediator,
            scheduled_at=scheduled_at,
            zoom_link=join_url,
            host_link=host_url,
        )

        dispute.status = "mediation_scheduled"
        dispute.mediator = mediator
        dispute.save()

        mediator_name = mediator.user.get_full_name() or mediator.user.username
        mediator_email = mediator.user.email

        # Send Message 8: Notify mediator
        if mediator_email:
            send_message_8_mediator_assigned_mediator.delay(
                to_email=mediator_email,
                mediator_name=mediator_name,
                case_id=dispute.id,
            )
        
        # Send Message 8: Notify parties
        send_message_8_mediator_assigned_parties.delay(
            applicant_email=dispute.applicant_email,
            respondent_email=dispute.respondent_email,
            mediator_name=mediator_name,
            case_id=dispute.id,
        )

        AuditLog.objects.create(
            dispute=dispute,
            user=request.user,
            action=f"Mediator {mediator_name} assigned, session scheduled for {scheduled_at}",
        )

        messages.success(request, f"Mediator assigned! Session scheduled for {scheduled_at}.")
        return redirect("dashboard:dispute_list")
    
    return render(request, "dashboard/assign_mediator.html", {"dispute": dispute, "mediators": mediators})
