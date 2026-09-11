from django.contrib import admin

from .models import BOMLine, BOMVersion, IssueRecord, Material, Product, SubstituteRule


class BOMLineInline(admin.TabularInline):
    model = BOMLine
    extra = 0


class SubstituteRuleInline(admin.TabularInline):
    model = SubstituteRule
    extra = 0


@admin.register(BOMVersion)
class BOMVersionAdmin(admin.ModelAdmin):
    list_display = ["product", "version", "status", "published_at"]
    inlines = [BOMLineInline, SubstituteRuleInline]


admin.site.register([Material, Product, IssueRecord])
