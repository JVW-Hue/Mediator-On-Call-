from django.db import models
from django.core.validators import FileExtensionValidator
from django.utils import timezone
import uuid


class Dispute(models.Model):
    DISPUTE_TYPES = [
        ("civil", "Civil"),
        ("commercial", "Commercial"),
        ("community", "Community"),
        ("construction", "Construction"),
        ("contractual", "Contractual"),
        ("criminal", "Criminal"),
        ("customary", "Customary"),
        ("damages", "Damages"),
        ("debts", "Debts"),
        ("divorce", "Divorce"),
        ("family", "Family"),
        ("labour", "Labour"),
        ("lease", "Lease"),
        ("loans", "Loans"),
        ("property", "Property"),
        ("religion", "Religion"),
        ("sales", "Sales"),
    ]

    STATUS_CHOICES = [
        ("submitted", "Submitted"),
        ("screening", "Under Screening"),
        ("rejected", "Rejected - Not Mediatable"),
        ("mediator_assigned", "Mediator Assigned - Awaiting Applicant Confirmation"),
        ("applicant_confirmed", "Applicant Confirmed - Awaiting Respondent"),
        ("forwarded", "Forwarded to Respondent"),
        ("responded", "Respondent Responded"),
        ("respondent_agreed", "Respondent Agreed - Awaiting Applicant Final Confirmation"),
        ("ready_for_assignment", "Ready for Mediator Assignment"),
        ("mediator_assigned", "Mediator Assigned"),
        ("mediation_scheduled", "Mediation Scheduled"),
        ("mediated", "Mediation Completed"),
        ("closed", "Closed"),
        ("arbitration", "Referred to Arbitration"),
        ("respondent_no_response", "Respondent No Response"),
    ]

    # New fields for mediator acceptance workflow
    mediator = models.ForeignKey(
        "Mediator",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_disputes",
    )
    mediator_accepted_at = models.DateTimeField(null=True, blank=True)
    applicant_confirmed_at = models.DateTimeField(null=True, blank=True)
    applicant_amended_details = models.TextField(blank=True)
    respondent_notified_at = models.DateTimeField(null=True, blank=True)
    respondent_response_deadline = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    
    # Mutual agreement workflow fields (also used by mediator workflow)
    respondent_agreed_at = models.DateTimeField(null=True, blank=True)
    applicant_final_confirmed_at = models.DateTimeField(null=True, blank=True)

    # Applicant (individual only)
    applicant_name = models.CharField(max_length=100)
    applicant_surname = models.CharField(max_length=100)
    applicant_cell = models.CharField(max_length=20)
    applicant_email = models.EmailField(blank=True)

    # Respondent (individual or business)
    respondent_type = models.CharField(
        max_length=10,
        choices=[("ind", "Individual"), ("bus", "Business")],
    )
    # if individual
    respondent_name = models.CharField(max_length=100, blank=True)
    respondent_surname = models.CharField(max_length=100, blank=True)
    respondent_cell = models.CharField(max_length=20, blank=True)
    # if business
    business_name = models.CharField(max_length=200, blank=True)
    owner_name = models.CharField(max_length=100, blank=True)
    owner_surname = models.CharField(max_length=100, blank=True)
    business_cell = models.CharField(max_length=20, blank=True)
    respondent_email = models.EmailField(blank=True)

    dispute_type = models.CharField(max_length=20, choices=DISPUTE_TYPES)
    description = models.TextField(blank=True)
    mediation_location = models.CharField(max_length=200, blank=True)
    preferred_date = models.DateTimeField(null=True, blank=True)
    summary = models.TextField(blank=True)
    photo = models.ImageField(
        upload_to="dispute_photos/",
        blank=True,
        null=True,
        help_text="Take a photo to support your dispute",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="submitted",
    )

    # screening fields (filled by admin)
    is_mediatable = models.BooleanField(null=True, blank=True)
    screening_notes = models.TextField(blank=True)
    screened_by = models.ForeignKey(
        'auth.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="screened_disputes",
    )
    screened_at = models.DateTimeField(null=True, blank=True)

    # unique token for respondent link (active 30 days)
    respondent_token = models.UUIDField(default=uuid.uuid4, unique=True)
    token_created_at = models.DateTimeField(auto_now_add=True)

    # token for applicant to view defence
    applicant_view_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    def __str__(self) -> str:
        return f"Dispute #{self.id} - {self.applicant_surname}"
    
    @property
    def is_eligible(self):
        return self.dispute_type not in ['family', 'labour', 'property']


class MediatableCase(models.Model):
    dispute = models.OneToOneField(
        Dispute,
        on_delete=models.CASCADE,
        related_name="mediatable_case",
    )
    accepted_at = models.DateTimeField(auto_now_add=True)
    accepted_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name="mediatable_cases",
    )
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Mediatable Case - Dispute #{self.dispute_id}"


class ReferredCase(models.Model):
    REFERRAL_CHOICES = [
        ("legal", "Legal Aid"),
        ("court", "Court"),
        ("police", "Police"),
        ("labour", "Labour Department"),
        ("family", "Family Services"),
        ("foresolve", "Foresolve"),
        ("other", "Other"),
    ]

    dispute = models.OneToOneField(
        Dispute,
        on_delete=models.CASCADE,
        related_name="referred_case",
    )
    referred_to = models.CharField(max_length=20, choices=REFERRAL_CHOICES)
    referred_at = models.DateTimeField(auto_now_add=True)
    referred_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name="referred_cases",
    )
    notes = models.TextField(blank=True)
    referral_details = models.TextField(blank=True)

    def __str__(self):
        return f"Referred Case - Dispute #{self.dispute_id} -> {self.get_referred_to_display()}"


class DisputeDocument(models.Model):
    dispute = models.ForeignKey(
        Dispute,
        related_name="documents",
        on_delete=models.CASCADE,
    )
    file = models.FileField(
        upload_to="dispute_docs/",
        validators=[FileExtensionValidator(["pdf", "jpg", "jpeg", "png"])],
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)


class DisputePhoto(models.Model):
    dispute = models.ForeignKey(
        Dispute,
        related_name="photos",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    image = models.ImageField(upload_to="dispute_photos/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Photo for Dispute #{self.dispute_id if self.dispute else 'Temp'}"


class TempDisputePhoto(models.Model):
    """Temporary storage for photos before dispute is created"""
    session_key = models.CharField(max_length=40)
    image = models.ImageField(upload_to="temp_photos/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Temp Photo {self.id}"


class RespondentResponse(models.Model):
    dispute = models.OneToOneField(
        Dispute,
        on_delete=models.CASCADE,
        related_name="response",
    )
    consent_to_mediate = models.BooleanField(default=False)
    agreed_to_rules = models.BooleanField(default=False)
    defence_explanation = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Response for dispute #{self.dispute_id}"


class ResponseDocument(models.Model):
    response = models.ForeignKey(
        RespondentResponse,
        related_name="documents",
        on_delete=models.CASCADE,
    )
    file = models.FileField(
        upload_to="response_docs/",
        validators=[FileExtensionValidator(["pdf", "jpg", "jpeg", "png"])],
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)


class Mediator(models.Model):
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE, related_name='mediator')
    cell = models.CharField(max_length=20)

    def __str__(self) -> str:
        return self.user.get_full_name() or self.user.username


class MediationSession(models.Model):
    dispute = models.OneToOneField(
        Dispute,
        on_delete=models.CASCADE,
        related_name="mediation",
    )
    mediator = models.ForeignKey(
        Mediator,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sessions",
    )
    scheduled_at = models.DateTimeField()
    zoom_link = models.URLField()
    outcome = models.TextField(blank=True)
    outcome_file = models.FileField(
        upload_to="outcomes/",
        blank=True,
    )
    arbitration_agreement = models.FileField(
        upload_to="arbitration/",
        blank=True,
    )
    pre_arbitration_minute = models.FileField(
        upload_to="arbitration/",
        blank=True,
    )

    def __str__(self) -> str:
        return f"Mediation for dispute #{self.dispute_id}"


class AuditLog(models.Model):
    dispute = models.ForeignKey(
        Dispute,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    user = models.ForeignKey(
        'auth.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dispute_audit_logs",
    )
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"AuditLog(dispute={self.dispute_id}, action={self.action})"


class RespondentToken(models.Model):
    dispute = models.ForeignKey(Dispute, on_delete=models.CASCADE, related_name='respondent_tokens')
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    email = models.EmailField()
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    
    def __str__(self):
        return f"Token for {self.email} - Dispute #{self.dispute_id}"
    
    def is_valid(self):
        return not self.used and self.expires_at > timezone.now()


class CalendarNote(models.Model):
    """Notes added to the calendar by staff/mediators."""
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='calendar_notes')
    date = models.DateField()
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
    
    def __str__(self):
        return f"Note for {self.date}: {self.note[:50]}"

