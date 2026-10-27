from django.urls import re_path

from report.views import (
    ReportDesignView,
    ReportDownloadView,
    ReportPreviewView,
    ReportsView,
)

app_name = "report"

urlpatterns = [
    re_path(r"^list$", ReportsView.as_view(), name="reports_list"),
    re_path(
        r"^(?P<report_id>\w+)/?$",
        ReportDesignView.as_view(),
        name="report_designer",
    ),
    re_path(
        r"^preview/(?P<report_id>\w+)/?$",
        ReportPreviewView.as_view(),
        name="report_preview",
    ),
    re_path(
        r"^download/(?P<report_id>\w+)/(?P<format>\w+)/?$",
        ReportDownloadView.as_view(),
        name="report_download",
    ),
    re_path(r"$", ReportDesignView.as_view(), name="report_designer"),
]
