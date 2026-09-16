import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Preformatted

OUT = Path(__file__).with_name("FarmOS-Frontend-Integration-Guide.pdf")
blue = colors.HexColor("#123B52")
teal = colors.HexColor("#087E8B")
green = colors.HexColor("#16804B")
orange = colors.HexColor("#D97706")
purple = colors.HexColor("#6D28D9")
ink = colors.HexColor("#263238")
light = colors.HexColor("#F1F6F8")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBrand", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=23, leading=28, textColor=blue, alignment=1, spaceAfter=7))
styles.add(ParagraphStyle(name="Sub", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#52636B"), alignment=1, spaceAfter=14))
styles.add(ParagraphStyle(name="H1Brand", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=19, textColor=blue, spaceBefore=12, spaceAfter=8))
styles.add(ParagraphStyle(name="H2Brand", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=teal, spaceBefore=9, spaceAfter=5))
styles.add(ParagraphStyle(name="BodyGuide", parent=styles["BodyText"], fontSize=9, leading=12, textColor=ink, spaceAfter=5))
styles.add(ParagraphStyle(name="CodeGuide", fontName="Courier", fontSize=7.3, leading=9, textColor=colors.HexColor("#17202A"), backColor=colors.HexColor("#F7F9FA"), borderColor=colors.HexColor("#D4E0E4"), borderWidth=.5, borderPadding=7, leftIndent=4, rightIndent=4))
styles.add(ParagraphStyle(name="White", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=8, textColor=colors.white))

def P(text, style="BodyGuide"):
    return Paragraph(text, styles[style])

def code(value):
    return Preformatted(json.dumps(value, indent=2), styles["CodeGuide"])

def method_label(method, path):
    palette = {"GET": teal, "POST": green, "PATCH": orange, "PUT": purple, "DELETE": colors.HexColor("#B42318")}
    return Table([[P(method, "White"), P(path, "White")]], colWidths=[20*mm, 155*mm], style=TableStyle([("BACKGROUND", (0,0), (0,0), palette[method]), ("BACKGROUND", (1,0), (1,0), blue), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("LEFTPADDING", (0,0), (-1,-1), 7), ("RIGHTPADDING", (0,0), (-1,-1), 7), ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))

def endpoint(method, path, purpose, request=None, response=None, notes=None):
    flow = [method_label(method, path), P("<b>Purpose:</b> " + purpose)]
    if request is not None:
        flow += [P("<b>Request JSON</b>"), code(request)]
    if response is not None:
        flow += [P("<b>Response JSON</b>"), code(response)]
    if notes:
        flow += [P("<b>Frontend notes:</b> " + notes)]
    flow.append(Spacer(1, 6))
    return flow

story = [Spacer(1, 10*mm), Paragraph("FarmOS Domain 01 API Integration Guide", styles["TitleBrand"]), Paragraph("Identity, authentication, organization, roles, assignments, access governance, and audit  |  API v2.2", styles["Sub"]), P("Scope: this guide is strictly limited to the locked Domain 01 correction. Animal, Health, and Operations APIs are intentionally excluded and are not reviewed or approved by this document."), P("Backend authorization remains authoritative; the frontend must not infer permission from role names."), Spacer(1, 6), Paragraph("1. Integration sequence", styles["H1Brand"]), P("Follow this order after the user opens the application:"), P("1. Send the channel header. 2. Log in. 3. Store cookies automatically. 4. Fetch the current user profile. 5. Fetch capabilities and navigation. 6. Render only permitted governance screens. 7. Call organization/farm endpoints with authorized identifiers. 8. Handle structured error codes."), Paragraph("Required headers", styles["H2Brand"]), code({"Content-Type": "application/json", "X-App-Channel": "web", "X-CSRFToken": "value-from-client_csrf_token"}), P("Use X-App-Channel: mobile for the mobile client. Do not store access or refresh tokens in browser localStorage; the backend uses secure cookies."), Paragraph("2. Standard response envelopes", styles["H1Brand"]), P("Every v2 endpoint returns a predictable JSON envelope. Read data from data and pagination information from meta."), code({"success": True, "code": "REQUEST_SUCCESSFUL", "message": "Request completed successfully.", "data": {"id": 123}, "meta": None}), code({"success": False, "code": "PERMISSION_DENIED", "message": "You do not have permission to perform this action.", "data": None, "errors": {}, "retryable": False}), PageBreak()]

story += [Paragraph("3. Authentication and bootstrap", styles["H1Brand"])]
story += endpoint("POST", "/api/auth/login", "Authenticate an active user and create the secure Web/Mobile session.", {"email": "owner@example.com", "password": "your-password"}, {"status": "Success", "message": "Login successful", "is_admin": False}, "The response sets client_access_token, client_refresh_token, and client_csrf_token cookies. A deactivated account returns ACCOUNT_DEACTIVATED.")
story += endpoint("GET", "/api/v2/users/me/", "Load the signed-in user identity, organization, ownership, assignments, and channel access.", response={"success": True, "code": "REQUEST_SUCCESSFUL", "data": {"identity": {"id": "uuid", "display_name": "Ada Farmer", "email": "owner@example.com"}, "access": {"account_type": "organization_owner", "access_source": "organization_ownership", "scope": "organization", "is_organization_owner": True, "all_farms": True, "assignments": []}, "channel_access": {"web": True, "mobile": False}}}, notes="Use this response to build the account shell. Owner status is a boolean/context decision, not a role-name comparison.")
story += endpoint("GET", "/api/v2/users/me/capabilities/", "Load effective capabilities and navigation primitives.", response={"success": True, "data": {"permissions": ["view_animal_details", "view_operation"], "capabilities": {"view_animal_details": True, "create_operation": False}, "navigation": {"livestock": True, "operations": True, "people": False}, "channel_access": {"web": True, "mobile": True}}}, notes="Render actions from capabilities. Do not assume Farm Manager or Veterinarian authority from labels.")
story += endpoint("POST", "/api/auth/refresh-token", "Renew an expired access session using the refresh cookie.", response={"success": True, "message": "Token refreshed"}, notes="If renewal fails, redirect to login. Deactivation cannot be bypassed through refresh.")
story += endpoint("POST", "/api/auth/signout", "Terminate the current authenticated session.", response={"success": True, "message": "Logged out successfully"}, notes="After logout, protected requests must fail; the account remains eligible for a fresh login.")

story += [Paragraph("4. Organization and people", styles["H1Brand"])]
story += endpoint("GET", "/api/v2/users/?page=1&page_size=20", "List members of the authenticated organization.", response={"success": True, "data": [{"id": "uuid", "display_name": "Ada Farmer", "email": "owner@example.com", "account_status": "active", "owner": True}], "meta": {"pagination": {"page": 1, "page_size": 20, "total_items": 1, "total_pages": 1}}}, notes="The owner field is a boolean. Search with ?search=. Never filter another organization in the frontend.")
story += endpoint("PATCH", "/api/v2/users/me/", "Update permitted personal profile fields only.", {"display_name": "Ada Farmer", "phone": "08012345678"}, {"success": True, "code": "PROFILE_UPDATED", "message": "Profile updated successfully.", "data": {"user": {"display_name": "Ada Farmer", "phone": "08012345678"}}}, "Any authenticated active user may update their own display_name and phone. Do not send role, permissions, farm_assignment, account_status, or organization_ownership; those fields are rejected.")
story += endpoint("POST", "/api/v2/users/me/avatar/", "Upload or replace the current user's profile picture using multipart/form-data.", "multipart/form-data: avatar=@profile.jpg (JPG or PNG, maximum 5 MB)", {"success": True, "code": "PROFILE_IMAGE_UPDATED", "message": "Profile picture updated successfully.", "data": {"avatar_url": "https://api.example.com/media/avatars/profile.jpg"}}, "Any authenticated active user may manage their own picture. Send the file as avatar; do not send JSON for this request.")
story += endpoint("DELETE", "/api/v2/users/me/avatar/", "Remove the current user's profile picture without deleting the account or profile.", None, {"success": True, "code": "PROFILE_IMAGE_REMOVED", "message": "Profile picture removed successfully.", "data": {"avatar_url": None}}, "The operation affects only the signed-in user's avatar. Deactivated users cannot call protected profile endpoints.")
story += endpoint("GET", "/api/v2/organizations/{organization_id}/", "Read the organization profile and ownership context.", response={"success": True, "data": {"id": "uuid", "name": "Green Valley Farm", "country": "Nigeria", "state_region": "Lagos", "owner": {"id": "uuid", "is_owner": True}}})

story += [Paragraph("5. Account-state lifecycle", styles["H1Brand"]), P("Account state is evaluated on login, protected requests, and refresh. The lifecycle is ACTIVE → DEACTIVATED → REACTIVATED. Deactivation preserves profile, assignment history, and audit history; it does not delete the user."), code({"account_status": "active"})]
story += endpoint("POST", "/api/v2/users/{user_id}/deactivate/", "Deactivate a staff account from an authorized governance context.", {"reason": "No longer employed"}, {"success": True, "data": {"user_id": "uuid", "account_status": "deactivated"}}, notes="Existing sessions fail on the next protected request. Fresh login and refresh return ACCOUNT_DEACTIVATED.")
story += endpoint("POST", "/api/v2/users/{user_id}/reactivate/", "Restore account eligibility without recreating revoked assignments.", response={"success": True, "data": {"user_id": "uuid", "account_status": "active"}}, notes="The user may log in again; effective access is recalculated from current membership and assignments.")

story += [Paragraph("6. Audit and security events", styles["H1Brand"]), P("The backend emits durable security/access events. The frontend should display structured event fields and must never parse a generic summary string."), code({"event_name": "USER_ASSIGNMENT_UPDATED", "actor_id": "uuid", "target_id": "assignment-id", "organization_id": "uuid", "farm_id": 1, "timestamp": "2026-09-16T08:00:00Z", "previous_state": {"farm_id": 1}, "new_state": {"farm_id": 2}, "result": "success", "source": "api"}), P("Implemented event names include USER_LOGGED_IN, USER_LOGGED_OUT, USER_DEACTIVATED, USER_REACTIVATED, USER_ASSIGNMENT_CREATED, USER_ASSIGNMENT_UPDATED, USER_ASSIGNMENT_REVOKED, ROLE_CREATED, ROLE_UPDATED, ROLE_PERMISSIONS_UPDATED, ORGANIZATION_CREATED, and FARM_CREATED."), P("Evidence: the development test suite verifies login, assignment, deactivation/reactivation, audit context, timestamps, result/source fields, and exclusion of passwords, access tokens, refresh tokens, and CSRF secrets."), PageBreak()]

story += [Paragraph("7. Organization farms", styles["H1Brand"])]
story += endpoint("GET", "/api/v2/organizations/{organization_id}/farms/", "List farms visible to the current user.", response={"success": True, "data": [{"id": 1, "name": "North Farm", "farm_code": "FRM-001", "status": "active"}], "meta": {"pagination": {"page": 1, "page_size": 20, "total_items": 1}}}, notes="Use returned farm IDs for subsequent scoped requests.")
story += endpoint("GET", "/api/v2/farms/{farm_id}/", "Read a farm profile and scoped counts.", response={"success": True, "data": {"id": 1, "organization_id": "uuid", "name": "North Farm", "status": "active", "counts": {"animals": 42, "open_tasks": 3}}})

story += [Paragraph("8. Roles, assignments, and channel rules", styles["H1Brand"]), P("Role and assignment administration is available to owners or users with the relevant governance capability."), code({"staff_role_templates": {"Farm Manager": {"web": True, "mobile": True}, "Veterinarian": {"web": True, "mobile": True}, "Field Worker": {"web": False, "mobile": True}}}), P("Organization Owner is deliberately absent from role_templates: Owner authority comes from organization ownership, not a staff role."), P("Assignment payload:"), code({"user_id": "uuid", "role_id": 3, "farm_id": 1, "client_request_id": "assignment-001"}), P("A revoked assignment remains in history but no longer grants current farm authority. A Field Worker calling a Web-protected endpoint receives CHANNEL_ACCESS_DENIED.")]

story += [Paragraph("9. Error handling and retry behavior", styles["H1Brand"]), code({"success": False, "code": "FARM_ACCESS_DENIED", "message": "You do not have access to this farm.", "data": None, "errors": {}, "retryable": False}), P("Handle codes, not message text. Recommended frontend actions:"), P("AUTHENTICATION_REQUIRED / SESSION_EXPIRED → refresh once or redirect to login. ACCOUNT_DEACTIVATED → sign out and show account notice. PERMISSION_DENIED / FARM_ACCESS_DENIED / CHANNEL_ACCESS_DENIED → show access-denied state. VALIDATION_ERROR → show field errors. CONFLICT → preserve the server result or ask the user to resolve the conflict."), Paragraph("10. Implementation evidence", styles["H1Brand"]), P("The development Docker verification currently reports 40 automated tests passed and 27 account/API end-to-end checks passed. These tests cover ownership, bootstrap, role templates, assignments, channels, deactivation/reactivation, refresh, logout, isolation, audit context, stable errors, soft removal, and sequential idempotency. Concurrent duplicate requests remain a separate QA item."), Paragraph("11. Implementation checklist", styles["H1Brand"]), P("✓ Send X-App-Channel.  ✓ Use secure cookies.  ✓ Bootstrap with /users/me/ and /users/me/capabilities/.  ✓ Use capability booleans for UI actions.  ✓ Include farm_id on scoped writes.  ✓ Include client_request_id on retryable material writes.  ✓ Read data from the standard envelope.  ✓ Never parse exception text.  ✓ Never allow frontend-only tenant filtering.  ✓ Use multipart/form-data for avatar uploads; enforce JPG/PNG and 5 MB maximum."), Spacer(1, 8), P("Contract reference: FarmOS Frontend API Contract v2.2. Domain 01 scope only. Backend base URL for Docker development: http://127.0.0.1:8082.")]

def footer(canvas, doc):
    canvas.saveState(); canvas.setFillColor(blue); canvas.rect(0, 0, A4[0], 8*mm, fill=1, stroke=0); canvas.setFillColor(colors.white); canvas.setFont('Helvetica', 7); canvas.drawString(18*mm, 3*mm, 'FarmOS | Frontend Integration Guide v2.2'); canvas.drawRightString(A4[0]-18*mm, 3*mm, 'Page %d' % doc.page); canvas.restoreState()

SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=14*mm, bottomMargin=15*mm, title='FarmOS Frontend Integration Guide', author='FarmOS Engineering').build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
