from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI
from account.api import router
from organization.api import router as organization



from django.conf import settings
from django.conf.urls.static import static

api = NinjaAPI(
    title="FarmOS API DOCS",
    version="1.0",
    description="API documentation",
    docs_url="/docs",  # Swagger UI (enabled by default)
    openapi_url="/openapi.json",  # Required for documentation to work
)
api.add_router("/auth/", router)
api.add_router("/organization/", organization)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
