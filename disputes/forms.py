from django import forms
from django.core.validators import RegexValidator
from .models import Dispute, DisputeDocument, RespondentResponse, ResponseDocument, MediationSession


class HoneypotField(forms.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("label", "Leave this empty")
        kwargs.setdefault("widget", forms.HiddenInput())
        super().__init__(*args, **kwargs)

    def clean(self, value):
        if value:
            raise forms.ValidationError("Spam detected.")
        return ""


phone_validator = RegexValidator(r'^\d+$', 'Please enter numbers only.')


class DisputeForm(forms.ModelForm):
    honeypot = HoneypotField()
    applicant_name = forms.CharField(
        required=True,
        error_messages={'required': 'Please enter your first name'},
        widget=forms.TextInput(attrs={"placeholder": "Enter your first name"}),
    )
    applicant_surname = forms.CharField(
        required=True,
        error_messages={'required': 'Please enter your last name'},
        widget=forms.TextInput(attrs={"placeholder": "Enter your last name"}),
    )
    applicant_cell = forms.CharField(
        required=True,
        validators=[phone_validator],
        error_messages={'required': 'Please enter your cell phone number'},
        widget=forms.TextInput(attrs={"placeholder": "e.g. 0821234567", "maxlength": "20"}),
    )
    applicant_email = forms.EmailField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Enter your email address (optional)"}),
    )
    respondent_type = forms.ChoiceField(
        required=True,
        choices=[('ind', 'Individual'), ('bus', 'Business')],
        error_messages={'required': 'Please select a respondent type'},
    )
    respondent_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Enter respondent's first name"}),
    )
    respondent_surname = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Enter respondent's last name (optional)"}),
    )
    respondent_cell = forms.CharField(
        required=False,
        validators=[phone_validator],
        widget=forms.TextInput(attrs={"placeholder": "Enter respondent's cell (optional)"}),
    )
    respondent_email = forms.EmailField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Enter respondent's email (optional)"}),
    )
    business_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Enter business name"}),
    )
    owner_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Enter owner/representative's first name"}),
    )
    owner_surname = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Enter owner/representative's last name (optional)"}),
    )
    business_cell = forms.CharField(
        required=False,
        validators=[phone_validator],
        widget=forms.TextInput(attrs={"placeholder": "Enter business cell (optional)"}),
    )
    dispute_type = forms.ChoiceField(
        required=True,
        choices=[('', 'Select dispute type...')] + [
            ('civil', 'Civil'),
            ('commercial', 'Commercial'),
            ('community', 'Community'),
            ('construction', 'Construction'),
            ('contractual', 'Contractual'),
            ('criminal', 'Criminal'),
            ('customary', 'Customary'),
            ('damages', 'Damages'),
            ('debts', 'Debts'),
            ('divorce', 'Divorce'),
            ('family', 'Family'),
            ('labour', 'Labour'),
            ('lease', 'Lease'),
            ('loans', 'Loans'),
            ('property', 'Property'),
            ('religion', 'Religion'),
            ('sales', 'Sales'),
        ],
        error_messages={'required': 'Please select a dispute type'},
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Describe your dispute in detail..."}),
    )
    mediation_location = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Johannesburg, Cape Town"}),
    )
    preferred_date = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    summary = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Brief summary for mediator..."}),
    )

    class Meta:
        model = Dispute
        fields = [
            "applicant_name",
            "applicant_surname",
            "applicant_cell",
            "applicant_email",
            "respondent_type",
            "respondent_name",
            "respondent_surname",
            "respondent_cell",
            "business_name",
            "owner_name",
            "owner_surname",
            "business_cell",
            "respondent_email",
            "dispute_type",
            "description",
            "mediation_location",
            "preferred_date",
            "summary",
        ]

    def clean(self):
        cleaned = super().clean()
        rtype = cleaned.get("respondent_type")
        if rtype == "bus":
            if not cleaned.get("business_name"):
                self.add_error("business_name", "Please enter the business name")
            if not cleaned.get("owner_name"):
                self.add_error("owner_name", "Please enter the owner/representative's first name")
        else:
            if not cleaned.get("respondent_name"):
                self.add_error("respondent_name", "Please enter the respondent's first name")
        return cleaned


DisputeDocumentFormSet = forms.modelformset_factory(
    DisputeDocument,
    fields=("file",),
    extra=1,
    max_num=5,
    can_delete=True,
    widgets={"file": forms.FileInput(attrs={"accept": "image/*,application/pdf"})},
)


class RespondentResponseForm(forms.ModelForm):
    class Meta:
        model = RespondentResponse
        fields = [
            "consent_to_mediate",
            "agreed_to_rules",
            "defence_explanation",
        ]
        widgets = {
            "defence_explanation": forms.Textarea(attrs={"rows": 4}),
        }


ResponseDocumentFormSet = forms.modelformset_factory(
    ResponseDocument,
    fields=("file",),
    extra=1,
    max_num=5,
    can_delete=True,
    widgets={"file": forms.FileInput(attrs={"accept": "image/*,application/pdf"})},
)


class MediationOutcomeForm(forms.ModelForm):
    arbitration = forms.BooleanField(required=False)

    class Meta:
        model = MediationSession
        fields = [
            "outcome",
            "outcome_file",
        ]
        widgets = {
            "outcome": forms.Textarea(attrs={"rows": 4}),
        }
