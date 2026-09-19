import json
from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase
from django.utils import timezone

from account.models import Country, AdminLevel1, EmailValidation, RefreshSession, User
from account.utils.jwt_utils import create_access_token, decode_token
from animals.models import Animal
from common.access import has_capability
from common.models import AuditLog
from operations.models import Task, IdempotencyKey
from organization.models import Organization, Farm, FarmType
from role.models import Role, Permission, RolePermission, UserRole
from role.templates import provision_templates, TEMPLATES


class Domain01Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.country = Country.objects.create(name="Nigeria")
        cls.state = AdminLevel1.objects.create(name="Lagos", country=cls.country)
        cls.owner = cls.make_user("owner")
        cls.org = Organization.objects.create(user=cls.owner, name="A", code="A", country=cls.country, state_region=cls.state)
        cls.owner.organization = cls.org
        cls.owner.save()
        provision_templates(cls.org)
        cls.ft = FarmType.objects.create(name="Livestock", code="livestock")
        cls.farm_a = Farm.objects.create(organization=cls.org, name="A", farm_code="A", farm_type=cls.ft)
        cls.farm_b = Farm.objects.create(organization=cls.org, name="B", farm_code="B", farm_type=cls.ft)
        cls.other_owner = cls.make_user("other_owner")
        cls.other_org = Organization.objects.create(user=cls.other_owner, name="Other", code="OTHER")
        cls.other_owner.organization = cls.other_org
        cls.other_owner.save()
        cls.other_farm = Farm.objects.create(organization=cls.other_org, name="Other", farm_code="OTHER", farm_type=cls.ft)
        cls.manager = cls.make_user("manager", cls.org)
        cls.vet = cls.make_user("vet", cls.org)
        cls.worker = cls.make_user("worker", cls.org)
        cls.unassigned = cls.make_user("unassigned", cls.org)
        for user, template in ((cls.manager, "farm_manager"), (cls.vet, "veterinarian"), (cls.worker, "field_worker")):
            UserRole.objects.create(user=user, farm=cls.farm_a,
                role=Role.objects.get(organization=cls.org, system_template_type=template), assigned_by=cls.owner)
        cls.animal_a = Animal.objects.create(farm=cls.farm_a, tag_id="ANIMAL-A", gender="female", source_type="opening_record", status="active")
        cls.animal_b = Animal.objects.create(farm=cls.farm_b, tag_id="ANIMAL-B", gender="female", source_type="opening_record", status="active")

    @staticmethod
    def make_user(name, org=None):
        user = User.objects.create_user(username=name, email=name+"@example.com", password="Domain01Pass!237", organization=org)
        EmailValidation.objects.create(email=user.email, code="123456", is_used=True, expires_at=timezone.now()+timedelta(days=1))
        return user

    def request(self, client, method, path, data=None, **headers):
        return getattr(client, method)(path, data=json.dumps(data or {}), content_type="application/json", **headers)

    def login(self, user=None, channel="web"):
        client = Client(HTTP_X_APP_CHANNEL=channel)
        response = self.request(client, "post", "/api/auth/login", {"email": (user or self.owner).email, "password": "Domain01Pass!237"})
        self.assertEqual(response.status_code, 200, response.content)
        return client

    def test_login_and_bootstrap(self):
        client = self.login()
        data = client.get("/api/v2/users/me/").json()["data"]
        self.assertEqual(data["access"]["access_source"], "organization_ownership")
        self.assertTrue(data["access"]["all_farms"])
        self.assertEqual(data["assignments"], [])
        self.assertTrue(data["channel_access"]["web"])
        self.assertTrue(AuditLog.objects.filter(action="USER_LOGGED_IN", user=self.owner).exists())

    def test_invalid_login_and_unauthenticated(self):
        for email in (self.owner.email, "unknown@example.com"):
            response = self.request(Client(), "post", "/api/auth/login", {"email": email, "password": "wrong"})
            self.assertEqual(response.status_code, 401)
        response = Client().get("/api/v2/users/me/")
        self.assertEqual(response.json()["code"], "AUTHENTICATION_REQUIRED")

    def test_owner_all_farms_without_assignment(self):
        client = self.login()
        self.assertFalse(UserRole.objects.filter(user=self.owner).exists())
        for farm in (self.farm_a, self.farm_b):
            response = client.get(f"/api/v2/farms/{farm.pk}/")
            self.assertEqual(response.status_code, 200, response.content)

    def test_organization_creation_without_industry_and_retry(self):
        user = self.make_user("new_owner")
        client = self.login(user)
        payload = {"name": "New", "country_id": self.country.pk, "state_region_id": self.state.pk, "client_request_id": "new-org"}
        first = self.request(client, "post", "/api/organization/organization/", payload)
        second = self.request(client, "post", "/api/organization/organization/", payload)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json(), second.json())
        org = Organization.objects.get(user=user)
        user.refresh_from_db()
        self.assertEqual(user.organization, org)
        self.assertEqual(Role.objects.filter(organization=org).count(), 3)
        self.assertFalse(UserRole.objects.filter(user=user).exists())

    def test_default_template_permission_sets(self):
        for template, (_, web, mobile, expected) in TEMPLATES.items():
            role = Role.objects.get(organization=self.org, system_template_type=template)
            actual = set(RolePermission.objects.filter(role=role).values_list("permission__code", flat=True))
            self.assertEqual(actual, expected)
            self.assertEqual((role.web_access, role.mobile_access), (web, mobile))
        self.assertFalse(has_capability(self.manager, self.org, "manage_people"))
        self.assertFalse(has_capability(self.worker, self.org, "create_operation"))
        self.assertFalse(has_capability(self.vet, self.org, "create_operation"))

    def test_permission_replacement_all_cardinalities(self):
        client = self.login()
        role = Role.objects.get(organization=self.org, system_template_type="farm_manager")
        permissions = list(Permission.objects.order_by("id").values_list("id", flat=True)[:2])
        for selected in ([], permissions[:1], permissions, permissions[:1], [], permissions):
            response = self.request(client, "post", "/api/role/role-permission/", {"role_id": role.pk, "permission_ids": selected})
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(set(RolePermission.objects.filter(role=role).values_list("permission_id", flat=True)), set(selected))
        provision_templates(self.org)
        self.assertEqual(RolePermission.objects.filter(role=role).count(), 2)

    def test_custom_role_names_do_not_grant_authority(self):
        client = self.login()
        response = self.request(client, "post", "/api/role/role/", {"name": "Organization Owner"})
        self.assertEqual(response.status_code, 200, response.content)
        role = Role.objects.get(organization=self.org, name="Organization Owner")
        UserRole.objects.create(user=self.unassigned, farm=self.farm_a, role=role)
        self.assertFalse(has_capability(self.unassigned, self.org, "manage_people"))

    def test_profile_rejects_governance_fields(self):
        client = self.login(self.manager)
        for field in ("role", "permissions", "farm_assignment", "account_status", "organization_ownership"):
            response = self.request(client, "patch", "/api/v2/users/me/", {field: "changed"})
            self.assertEqual(response.status_code, 422, response.content)
            self.assertEqual(response.json()["code"], "INVALID_PROFILE_FIELD")
        response = self.request(client, "patch", "/api/v2/users/me/", {"display_name": "A Manager", "phone": "08012345678"})
        self.assertEqual(response.status_code, 200, response.content)

    def test_channel_matrix(self):
        for user, web, mobile in ((self.owner, True, False), (self.manager, True, True), (self.vet, True, True), (self.worker, False, True)):
            for channel, allowed in (("web", web), ("mobile", mobile)):
                client = Client(HTTP_X_APP_CHANNEL=channel)
                response = self.request(client, "post", "/api/auth/login", {"email": user.email, "password": "Domain01Pass!237"})
                self.assertEqual(response.status_code, 200 if allowed else 403, response.content)
                if not allowed:
                    self.assertEqual(response.json()["code"], "CHANNEL_ACCESS_DENIED")
                else:
                    response = client.get("/api/v2/users/me/")
                    self.assertEqual(response.status_code, 200, response.content)

    def test_channel_cannot_switch_existing_session(self):
        client = self.login(self.worker, "mobile")
        response = client.get("/api/v2/users/me/", HTTP_X_APP_CHANNEL="web")
        self.assertEqual(response.json()["code"], "CHANNEL_ACCESS_DENIED")

    def test_farm_isolation_lists_details_and_writes(self):
        client = self.login(self.manager)
        response = client.get("/api/v2/animals/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([row["id"] for row in response.json()["data"]], [self.animal_a.pk])
        for path in (f"/api/v2/animals/{self.animal_b.pk}/profile/", f"/api/v2/farms/{self.farm_b.pk}/", f"/api/animals/animal-profile/v2/{self.animal_b.pk}"):
            self.assertIn(client.get(path).status_code, (403, 404), path)
        response = self.request(client, "patch", f"/api/v2/animals/{self.animal_b.pk}/", {"notes": "forbidden"})
        self.assertIn(response.status_code, (403, 404), response.content)
        response = self.request(client, "post", "/api/v2/animals/", {"farm_id": self.farm_b.pk, "gender": "female", "source_type": "opening_record"})
        self.assertIn(response.status_code, (403, 404), response.content)
        self.animal_b.refresh_from_db()
        self.assertEqual(self.animal_b.notes, "")

    def test_capability_is_required_for_protected_reads(self):
        client = self.login(self.manager)
        self.assertEqual(client.get("/api/v2/animals/").status_code, 200)

        manager_role = Role.objects.get(organization=self.org, system_template_type="farm_manager")
        RolePermission.objects.filter(role=manager_role).delete()

        for path in ("/api/v2/animals/", "/api/v2/operations/tasks/"):
            response = client.get(path)
            self.assertEqual(response.status_code, 403, response.content)
            self.assertEqual(response.json()["code"], "PERMISSION_DENIED")

    def test_farm_scope_is_required_even_with_capability(self):
        client = self.login(self.manager)
        for path in (
            f"/api/v2/farms/{self.farm_b.pk}/",
            f"/api/v2/farms/{self.farm_b.pk}/overview/",
            f"/api/v2/farms/{self.farm_b.pk}/timeline/",
        ):
            response = client.get(path)
            self.assertIn(response.status_code, (403, 404), response.content)

    def test_people_and_role_tenant_isolation(self):
        client = self.login()
        for query in (self.other_owner.email, "other_owner", str(self.other_owner.id)):
            response = client.get("/api/v2/search/", {"q": query})
            self.assertEqual(response.json()["data"]["people"], [])
        self.assertEqual(client.get(f"/api/v2/users/{self.other_owner.pk}/").status_code, 404)
        role = Role.objects.create(organization=self.other_org, name="Other", code="other")
        response = self.request(client, "patch", "/api/role/role/", {"role_id": role.pk, "name": "intrusion"})
        self.assertEqual(response.status_code, 404, response.content)
        role.refresh_from_db()
        self.assertEqual(role.name, "Other")

    def test_people_list_marks_organization_owner(self):
        client = self.login()
        response = client.get("/api/v2/users/")
        self.assertEqual(response.status_code, 200, response.content)
        members = {row["id"]: row for row in response.json()["data"]}
        self.assertTrue(members[str(self.owner.pk)]["owner"])
        self.assertFalse(members[str(self.manager.pk)]["owner"])

    def test_manager_has_no_default_people_admin(self):
        client = self.login(self.manager)
        for path in ("/api/v2/users/", "/api/v2/roles/", "/api/role/user/", "/api/role/role/"):
            response = client.get(path)
            self.assertEqual(response.status_code, 403, response.content)

    def test_assignment_lifecycle_and_audit(self):
        client = self.login()
        role = Role.objects.get(organization=self.org, system_template_type="farm_manager")
        payload = {"user_id": str(self.unassigned.pk), "role_id": role.pk, "farm_id": self.farm_a.pk, "client_request_id": "assignment"}
        first = self.request(client, "post", "/api/role/user-role/", payload)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json(), self.request(client, "post", "/api/role/user-role/", payload).json())
        assignment = UserRole.objects.get(user=self.unassigned)
        staff_client = self.login(self.unassigned)
        response = self.request(client, "patch", f"/api/role/user-role/{assignment.pk}/", {"farm_id": self.farm_b.pk})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(staff_client.get(f"/api/v2/farms/{self.farm_a.pk}/").status_code, 403)
        response = self.request(client, "delete", f"/api/role/user-role/{assignment.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, "revoked")
        self.assertIsNotNone(assignment.revoked_at)
        self.assertEqual(AuditLog.objects.filter(object_type="role.userrole", object_id=str(assignment.pk)).count(), 3)
        self.assertEqual(staff_client.get("/api/v2/users/me/").status_code, 200)
        self.assertNotEqual(staff_client.get(f"/api/v2/farms/{self.farm_b.pk}/").status_code, 200)

    def test_assigning_new_role_replaces_previous_role_on_farm(self):
        client = self.login()
        manager_role = Role.objects.get(organization=self.org, system_template_type="farm_manager")
        vet_role = Role.objects.get(organization=self.org, system_template_type="veterinarian")
        first = self.request(client, "post", "/api/role/user-role/", {
            "user_id": str(self.unassigned.pk), "role_id": manager_role.pk,
            "farm_id": self.farm_a.pk, "client_request_id": "replace-manager",
        })
        self.assertEqual(first.status_code, 200, first.content)
        second = self.request(client, "post", "/api/role/user-role/", {
            "user_id": str(self.unassigned.pk), "role_id": vet_role.pk,
            "farm_id": self.farm_a.pk, "client_request_id": "replace-vet",
        })
        self.assertEqual(second.status_code, 200, second.content)
        active = UserRole.objects.filter(user=self.unassigned, farm=self.farm_a, status="active")
        self.assertEqual(list(active.values_list("role_id", flat=True)), [vet_role.pk])
        self.assertEqual(UserRole.objects.get(user=self.unassigned, farm=self.farm_a, role=manager_role).status, "revoked")

    def test_role_deactivation_removes_current_access(self):
        client = self.login(self.manager)
        role = Role.objects.get(organization=self.org, system_template_type="farm_manager")
        self.assertEqual(client.get(f"/api/v2/farms/{self.farm_a.pk}/").status_code, 200)

        role.active = False
        role.save(update_fields=["active"])
        self.assertNotEqual(client.get(f"/api/v2/farms/{self.farm_a.pk}/").status_code, 200)

        role.active = True
        role.save(update_fields=["active"])
        self.assertEqual(client.get(f"/api/v2/farms/{self.farm_a.pk}/").status_code, 200)

    def test_owner_authority_is_not_granted_by_staff_assignment(self):
        client = self.login()
        owner_role = Role.objects.create(
            organization=self.org, name="Owner-like staff role", code="owner_like"
        )
        UserRole.objects.create(
            user=self.unassigned, farm=self.farm_a, role=owner_role, assigned_by=self.owner
        )
        staff_client = self.login(self.unassigned)
        self.assertIn(staff_client.get(f"/api/v2/farms/{self.farm_a.pk}/").status_code, (403, 404))
        self.assertEqual(client.get("/api/v2/users/").status_code, 200)

    def test_invalid_assignment_targets(self):
        client = self.login()
        role = Role.objects.get(organization=self.org, system_template_type="farm_manager")
        other_role = Role.objects.create(organization=self.other_org, name="Other", code="other")
        for user, r, farm in ((self.other_owner, role, self.farm_a), (self.manager, other_role, self.farm_a), (self.manager, role, self.other_farm), (self.owner, role, self.farm_a)):
            response = self.request(client, "post", "/api/role/user-role/", {"user_id": str(user.pk), "role_id": r.pk, "farm_id": farm.pk})
            self.assertIn(response.status_code, (403, 404, 422), response.content)

    def test_unassigned_identity_and_logout(self):
        client = self.login(self.unassigned)
        response = client.get("/api/v2/users/me/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["access"]["access_source"], "none")
        self.assertNotEqual(client.get("/api/v2/animals/").status_code, 200)
        self.assertEqual(self.request(client, "patch", "/api/v2/users/me/", {"display_name": "Unassigned"}).status_code, 200)
        self.assertEqual(self.request(client, "post", "/api/auth/signout").status_code, 200)

    def test_deactivation_existing_session_refresh_reactivation(self):
        owner = self.login()
        staff = self.login(self.manager)
        response = self.request(owner, "post", f"/api/v2/users/{self.manager.pk}/deactivate/", {"reason": "Test"})
        self.assertEqual(response.status_code, 200, response.content)
        for path in ("/api/v2/users/me/", "/api/auth/profile"):
            self.assertEqual(staff.get(path).json()["code"], "ACCOUNT_DEACTIVATED")
        self.assertEqual(self.request(staff, "post", "/api/auth/refresh-token").json()["code"], "ACCOUNT_DEACTIVATED")
        denied = self.request(Client(), "post", "/api/auth/login", {"email": self.manager.email, "password": "Domain01Pass!237"})
        self.assertEqual(denied.json()["code"], "ACCOUNT_DEACTIVATED")
        self.assertTrue(UserRole.objects.filter(user=self.manager).exists())
        response = self.request(owner, "post", f"/api/v2/users/{self.manager.pk}/reactivate/")
        self.assertEqual(response.status_code, 200, response.content)
        self.login(self.manager)
        self.assertEqual(staff.get("/api/v2/users/me/").status_code, 401)

    def test_owner_cannot_be_deactivated(self):
        client = self.login()
        response = self.request(client, "post", f"/api/v2/users/{self.owner.pk}/deactivate/")
        self.assertEqual(response.status_code, 403, response.content)

    def test_refresh_expired_access_and_replay(self):
        client = self.login()
        claims = decode_token(client.cookies["client_access_token"].value)
        client.cookies["client_access_token"] = create_access_token({"sub": claims["sub"], "sid": claims["sid"], "kind": "access"}, expires_delta=timedelta(seconds=-1))
        old_refresh = client.cookies["client_refresh_token"].value
        self.assertEqual(client.get("/api/v2/users/me/").status_code, 401)
        self.assertEqual(self.request(client, "post", "/api/auth/refresh-token").status_code, 200)
        self.assertEqual(client.get("/api/v2/users/me/").status_code, 200)
        client.cookies["client_refresh_token"] = old_refresh
        self.assertEqual(self.request(client, "post", "/api/auth/refresh-token").json()["code"], "SESSION_EXPIRED")
        self.assertEqual(RefreshSession.objects.filter(user=self.owner).count(), 1)

    def test_session_cookies_and_refresh_channel_binding(self):
        client = self.login(self.worker, "mobile")
        access_cookie = client.cookies["client_access_token"]
        refresh_cookie = client.cookies["client_refresh_token"]
        csrf_cookie = client.cookies["client_csrf_token"]
        self.assertTrue(access_cookie["httponly"])
        self.assertTrue(refresh_cookie["httponly"])
        self.assertFalse(csrf_cookie["httponly"])
        self.assertEqual(refresh_cookie["path"], "/api/auth/refresh-token")

        response = self.request(client, "post", "/api/auth/refresh-token", **{"HTTP_X_APP_CHANNEL": "web"})
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["code"], "CHANNEL_ACCESS_DENIED")

    def test_deactivated_account_cannot_refresh_or_login(self):
        owner = self.login()
        staff = self.login(self.manager)
        response = self.request(owner, "post", f"/api/v2/users/{self.manager.pk}/deactivate/", {"reason": "security test"})
        self.assertEqual(response.status_code, 200, response.content)
        refresh = self.request(staff, "post", "/api/auth/refresh-token")
        self.assertEqual(refresh.status_code, 403, refresh.content)
        self.assertEqual(refresh.json()["code"], "ACCOUNT_DEACTIVATED")
        login = self.request(Client(), "post", "/api/auth/login", {"email": self.manager.email, "password": "Domain01Pass!237"})
        self.assertEqual(login.status_code, 403, login.content)
        self.assertEqual(login.json()["code"], "ACCOUNT_DEACTIVATED")

    def test_logout_only_current_session(self):
        first, second = self.login(), self.login()
        old_access = first.cookies["client_access_token"].value
        self.assertEqual(self.request(first, "post", "/api/auth/signout").status_code, 200)
        first.cookies["client_access_token"] = old_access
        self.assertEqual(first.get("/api/v2/users/me/").status_code, 401)
        self.assertEqual(second.get("/api/v2/users/me/").status_code, 200)

    def test_task_completion_retry_exactly_once(self):
        client = self.login()
        task = Task.objects.create(organization=self.org, farm=self.farm_a, task_type="generic", title="Task", assigned_to=self.owner, created_by=self.owner, status="assigned")
        path = f"/api/v2/operations/tasks/{task.pk}/complete/"
        payload = {"client_request_id": "complete", "notes": "done"}
        first = self.request(client, "post", path, payload)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json(), self.request(client, "post", path, payload).json())
        from animals.models import AnimalEvent
        self.assertEqual(AnimalEvent.objects.filter(reference_table="task", reference_id=task.pk, event_type__name="task_completed").count(), 1)

    def test_failed_mutation_does_not_poison_key(self):
        client = self.login()
        payload = {"farm_id": self.other_farm.pk, "task_type": "generic", "title": "Retry", "client_request_id": "retry"}
        self.assertNotEqual(self.request(client, "post", "/api/v2/operations/tasks/", payload).status_code, 200)
        self.assertFalse(IdempotencyKey.objects.filter(key="retry").exists())
        payload["farm_id"] = self.farm_a.pk
        response = self.request(client, "post", "/api/v2/operations/tasks/", payload)
        self.assertEqual(response.status_code, 200, response.content)

    def test_security_audit_event_has_context_without_secrets(self):
        client = self.login()
        event = AuditLog.objects.filter(action="USER_LOGGED_IN", user=self.owner).latest("created_at")
        self.assertEqual(event.source_module, "domain01")
        self.assertEqual(event.object_type, "account.user")
        self.assertEqual(event.object_id, str(self.owner.pk))
        self.assertEqual(event.context["organization_id"], str(self.org.pk))
        self.assertEqual(event.context["result"], "success")
        serialized = json.dumps(event.context).lower()
        for secret in ("password", "access_token", "refresh_token", "csrf"):
            self.assertNotIn(secret, serialized)

    def test_stable_error_envelope_for_authentication_and_validation(self):
        response = self.client.get("/api/v2/users/me/")
        body = response.json()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(body["success"], False)
        self.assertEqual(body["code"], "AUTHENTICATION_REQUIRED")
        self.assertIn("message", body)
        self.assertIn("data", body)
        self.assertIn("errors", body)
        self.assertIn("retryable", body)

        client = self.login()
        response = self.request(client, "post", "/api/v2/operations/tasks/", {"farm_id": self.farm_a.pk})
        body = response.json()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(body["success"], False)
        self.assertEqual(body["code"], "VALIDATION_ERROR")
        self.assertIn("errors", body)

    def test_acceptance_error_codes_and_conflict_contract(self):
        unauthenticated = self.client.get("/api/v2/users/me/").json()
        self.assertEqual(unauthenticated["code"], "AUTHENTICATION_REQUIRED")

        client = self.login(self.manager)
        denied = client.get(f"/api/v2/farms/{self.farm_b.pk}/")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["code"], "FARM_ACCESS_DENIED")

        worker = self.login(self.worker, "mobile")
        self.assertEqual(worker.get("/api/v2/users/me/", HTTP_X_APP_CHANNEL="web").json()["code"], "CHANNEL_ACCESS_DENIED")

        expired = self.login()
        access = expired.cookies["client_access_token"].value
        claims = decode_token(access)
        expired.cookies["client_access_token"] = create_access_token(
            {"sub": claims["sub"], "sid": claims["sid"], "kind": "access"},
            expires_delta=timedelta(seconds=-1),
        )
        self.assertEqual(expired.get("/api/v2/users/me/").json()["code"], "SESSION_EXPIRED")

        owner = self.login()
        duplicate = self.request(owner, "post", "/api/organization/organization/", {
            "name": "Duplicate", "country_id": self.country.pk,
            "state_region_id": self.state.pk, "client_request_id": "acceptance-conflict",
        })
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["code"], "CONFLICT")

    def test_acceptance_audit_events_have_required_security_context(self):
        owner_client = self.login()
        role = Role.objects.get(organization=self.org, system_template_type="farm_manager")
        assignment_payload = {"user_id": str(self.unassigned.pk), "role_id": role.pk, "farm_id": self.farm_a.pk}
        self.request(owner_client, "post", "/api/role/user-role/", assignment_payload)
        assignment = UserRole.objects.get(user=self.unassigned)
        self.request(owner_client, "patch", f"/api/role/user-role/{assignment.pk}/", {"farm_id": self.farm_b.pk})
        self.request(owner_client, "delete", f"/api/role/user-role/{assignment.pk}/")
        self.request(owner_client, "post", f"/api/v2/users/{self.unassigned.pk}/deactivate/", {"reason": "acceptance"})
        self.request(owner_client, "post", f"/api/v2/users/{self.unassigned.pk}/reactivate/")
        actions = set(AuditLog.objects.filter(user=self.owner).values_list("action", flat=True))
        self.assertTrue({"USER_LOGGED_IN", "USER_ASSIGNMENT_CREATED", "USER_ASSIGNMENT_UPDATED",
                         "USER_ASSIGNMENT_REVOKED", "USER_DEACTIVATED", "USER_REACTIVATED"}.issubset(actions))
        for event in AuditLog.objects.filter(user=self.owner):
            self.assertIsNotNone(event.created_at)
            self.assertNotIn("password", json.dumps(event.context).lower())
            self.assertNotIn("access_token", json.dumps(event.context).lower())
            self.assertNotIn("refresh_token", json.dumps(event.context).lower())

    def test_acceptance_idempotency_prevents_duplicate_sensitive_writes(self):
        client = self.login()
        payload = {"farm_id": self.farm_a.pk, "task_type": "generic", "title": "Idempotent", "client_request_id": "acceptance-task"}
        first = self.request(client, "post", "/api/v2/operations/tasks/", payload)
        second = self.request(client, "post", "/api/v2/operations/tasks/", payload)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(Task.objects.filter(title="Idempotent").count(), 1)

    def test_acceptance_idempotency_farm_invitation_and_assignment(self):
        client = self.login()
        farm_payload = {
            "organization_id": str(self.org.pk), "name": "Retry Farm", "country_id": self.country.pk,
            "state_region_id": self.state.pk, "city": "Lagos", "location_address": "Test",
            "farm_type_id": self.ft.pk, "is_primary": False, "client_request_id": "retry-farm",
        }
        first = self.request(client, "post", "/api/organization/farm/", farm_payload)
        second = self.request(client, "post", "/api/organization/farm/", farm_payload)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(Farm.objects.filter(organization=self.org, name="Retry Farm").count(), 1)

        invite = {"email": "retry-invite@example.com", "client_request_id": "retry-invite"}
        first = self.request(client, "post", "/api/role/user/", invite)
        second = self.request(client, "post", "/api/role/user/", invite)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(User.objects.filter(email=invite["email"]).count(), 1)

        role = Role.objects.get(organization=self.org, system_template_type="farm_manager")
        assignment = {"user_id": str(self.unassigned.pk), "role_id": role.pk, "farm_id": self.farm_a.pk, "client_request_id": "retry-assignment"}
        first = self.request(client, "post", "/api/role/user-role/", assignment)
        second = self.request(client, "post", "/api/role/user-role/", assignment)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(UserRole.objects.filter(user=self.unassigned, farm=self.farm_a, status="active").count(), 1)

    def test_soft_remove_user_preserves_data_and_revokes_access(self):
        client = self.login()
        assignment = UserRole.objects.filter(user=self.manager).first()
        response = self.request(client, "delete", f"/api/v2/users/{self.manager.pk}/remove-from-organization/")
        self.assertEqual(response.status_code, 200, response.content)
        self.manager.refresh_from_db()
        assignment.refresh_from_db()
        self.assertIsNone(self.manager.organization_id)
        self.assertEqual(assignment.status, "revoked")
        self.assertTrue(User.objects.filter(pk=self.manager.pk).exists())
        self.assertEqual(response.json()["code"], "USER_REMOVED_FROM_ORGANIZATION")

    def test_soft_remove_protects_owner_and_self(self):
        client = self.login()
        for user in (self.owner,):
            response = self.request(client, "delete", f"/api/v2/users/{user.pk}/remove-from-organization/")
            self.assertEqual(response.status_code, 403, response.content)

    def test_openapi_references_resolve(self):
        from api.urls import api
        schema = api.get_openapi_schema()
        def walk(value):
            if isinstance(value, dict):
                if "$ref" in value and value["$ref"].startswith("#/"):
                    node = schema
                    for part in value["$ref"][2:].split("/"):
                        self.assertIn(part, node, value["$ref"])
                        node = node[part]
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
        walk(schema)
