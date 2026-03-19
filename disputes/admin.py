from django.contrib import admin
from django.contrib.auth.models import User
from .models import (
    Dispute,
    DisputeDocument,
    RespondentResponse,
    ResponseDocument,
    Mediator,
    MediationSession,
    MediatableCase,
    ReferredCase,
)


class DisputeDocumentInline(admin.TabularInline):
    model = DisputeDocument
    extra = 0


class RespondentResponseInline(admin.StackedInline):
    model = RespondentResponse
    extra = 0


class ResponseDocumentInline(admin.TabularInline):
    model = ResponseDocument
    extra = 0


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "applicant_name",
        "applicant_surname",
        "dispute_type",
        "status",
        "created_at",
    )
    list_filter = ("status", "dispute_type", "created_at")
    search_fields = ("applicant_name", "applicant_surname", "description")
    readonly_fields = ("respondent_token", "applicant_view_token", "created_at")
    fieldsets = (
        (
            "Applicant Information",
            {
                "fields": (
                    "applicant_name",
                    "applicant_surname",
                    "applicant_cell",
                    "applicant_email",
                )
            },
        ),
        (
            "Respondent Information",
            {
                "fields": (
                    "respondent_type",
                    "respondent_name",
                    "respondent_surname",
                    "respondent_cell",
                    "business_name",
                    "owner_name",
                    "owner_surname",
                    "business_cell",
                    "respondent_email",
                )
            },
        ),
        ("Dispute Details", {"fields": ("dispute_type", "description", "photo", "status")}),
        (
            "Screening",
            {"fields": ("is_mediatable", "screening_notes", "screened_by", "screened_at")},
        ),
        (
            "Tokens & Timestamps",
            {
                "fields": (
                    "respondent_token",
                    "applicant_view_token",
                    "token_created_at",
                    "created_at",
                )
            },
        ),
    )
    inlines = [DisputeDocumentInline, RespondentResponseInline]


@admin.register(DisputeDocument)
class DisputeDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "dispute", "uploaded_at")


@admin.register(RespondentResponse)
class RespondentResponseAdmin(admin.ModelAdmin):
    list_display = ("dispute", "consent_to_mediate", "created_at")
    inlines = [ResponseDocumentInline]


@admin.register(ResponseDocument)
class ResponseDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "response", "uploaded_at")


@admin.register(Mediator)
class MediatorAdmin(admin.ModelAdmin):
    list_display = ("user", "cell")


@admin.register(MediationSession)
class MediationSessionAdmin(admin.ModelAdmin):
    list_display = ("dispute", "mediator", "scheduled_at")


@admin.register(MediatableCase)
class MediatableCaseAdmin(admin.ModelAdmin):
    list_display = ("dispute", "accepted_at", "accepted_by", "notes")
    list_filter = ("accepted_at",)
    search_fields = ("dispute__applicant_name", "dispute__applicant_surname")


@admin.register(ReferredCase)
class ReferredCaseAdmin(admin.ModelAdmin):
    list_display = ("dispute", "referred_to", "referred_at", "referred_by")
    list_filter = ("referred_to", "referred_at")
    search_fields = ("dispute__applicant_name", "dispute__applicant_surname")


class CustomAdminSite(admin.AdminSite):
    def has_permission(self, request):
        if not request.user.is_active:
            return False
        if request.user.is_superuser:
            return True
        if request.user.is_staff:
            return True
        return False
    
    def admin_view(self, view, cacheable=False):
        inner = self._wrap_view(view)
        if settings.DEBUG:
            return inner
        return cacheable or settings.USE_I18N, (), inner

admin_site = CustomAdminSite(name='custom_admin')
admin_site.register(Dispute, DisputeAdmin)
admin_site.register(DisputeDocument, DisputeDocumentAdmin)
admin_site.register(RespondentResponse, RespondentResponseAdmin)
admin_site.register(ResponseDocument, ResponseDocumentAdmin)
admin_site.register(Mediator, MediatorAdmin)
admin_site.register(MediationSession, MediationSessionAdmin)
admin_site.register(MediatableCase, MediatableCaseAdmin)
admin_site.register(ReferredCase, ReferredCaseAdmin)
