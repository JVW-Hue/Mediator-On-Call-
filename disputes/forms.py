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
    photo = forms.ImageField(
        required=False,
        label="Take a Photo",
        help_text="Take a photo to support your dispute",
        widget=forms.FileInput(attrs={
            "accept": "image/*",
            "capture": "environment",
            "class": "form-control",
        }),
    )
    applicant_cell = forms.CharField(
        validators=[phone_validator],
        widget=forms.TextInput(attrs={"placeholder": "e.g. 0821234567", "pattern": r"\d*"}),
    )
    respondent_cell = forms.CharField(
        required=False,
        validators=[phone_validator],
        widget=forms.TextInput(attrs={"placeholder": "e.g. 0821234567", "pattern": r"\d*"}),
    )
    business_cell = forms.CharField(
        required=False,
        validators=[phone_validator],
        widget=forms.TextInput(attrs={"placeholder": "e.g. 0821234567", "pattern": r"\d*"}),
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
            "photo",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "respondent_name": forms.TextInput(attrs={"placeholder": "Required if Individual"}),
            "respondent_surname": forms.TextInput(attrs={"placeholder": "Required if Individual"}),
            "business_name": forms.TextInput(attrs={"placeholder": "Required if Business"}),
            "owner_name": forms.TextInput(attrs={"placeholder": "Required if Business"}),
            "owner_surname": forms.TextInput(attrs={"placeholder": "Required if Business"}),
            "mediation_location": forms.TextInput(attrs={"placeholder": "Location for mediation"}),
            "preferred_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "summary": forms.Textarea(attrs={"rows": 3, "placeholder": "Brief summary for mediator"}),
        }

    def clean(self):
        cleaned = super().clean()
        rtype = cleaned.get("respondent_type")
        if rtype == "bus":
            if not cleaned.get("business_name"):
                self.add_error("business_name", "Business name is required for business respondents.")
            if not cleaned.get("owner_name"):
                self.add_error("owner_name", "Owner name is required for business respondents.")
        else:
            if not cleaned.get("respondent_name"):
                self.add_error("respondent_name", "Respondent name is required for individuals.")
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
