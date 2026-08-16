from django.contrib import admin
from django.urls import path

admin.site.site_header = "Tati FarmOS"
admin.site.site_title = "Tati FarmOS Admin"
admin.site.index_title = "Platform Dashboard"
from ninja import NinjaAPI
from account.api import router
from organization.api import router as organization
from role.api import router as role
from admin_panel.api import router as admin_panel
from farms.api import router as farm
from core.api import router as global_api
from animals.api import router as animals
from reproduction.api import router as reproductions
from health.api import router as health
from feed.api import router as feed
from movement_records.api import router as movement_records
from alerts.api import router as alerts
from dashbaord.api import router as dashboard
from finance.api import router as finance
from pharmacy.api import router as pharmacy
from reports.api import router as reports
from django.conf import settings
from django.conf.urls.static import static

api = NinjaAPI(
    title="FarmOS API DOCS",
    version="1.0",
    description="API documentation",
    docs_url="/docs",  
    openapi_url="/openapi.json", 
)
api.add_router("/auth/", router)
api.add_router("/admin/", admin_panel)
api.add_router("/global/", global_api)
api.add_router("/organization/", organization)
api.add_router("/role/", role)
api.add_router("/farm/", farm)
api.add_router("/animals/", animals)
api.add_router("/reproductions/", reproductions)
api.add_router("/health/", health)
api.add_router("/feed/", feed)
api.add_router("/movement-records/", movement_records)
api.add_router("/alerts/", alerts)
api.add_router("/dashboard/", dashboard)
api.add_router("/finance/", finance)
api.add_router("/pharmacy/", pharmacy)
api.add_router("/reports/", reports)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
