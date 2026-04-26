from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI
from account.api import router
from organization.api import router as organization
from role.api import router as role
from admin_panel.api import router as admin_panel
from farms.api import router as farm
from core.api import router as global_api
from animals.api import router as animals
from reproduction.api import router as reproductions
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

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
