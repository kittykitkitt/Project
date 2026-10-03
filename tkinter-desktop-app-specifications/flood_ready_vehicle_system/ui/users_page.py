"""User administration (administrators only)."""
from __future__ import annotations

from typing import Any

from app.config import USER_ROLES
from . import TablePage
from .dialogs import DetailDialog, FormDialog, confirm, show_error, show_info


class UsersPage(TablePage):
    TITLE = "Users"
    SUBTITLE = "Accounts, roles and passwords"
    COLUMNS = [
        ("username", "Username", 140, "w"),
        ("full_name", "Full name", 220, "w"),
        ("role", "Role", 110, "w"),
        ("active", "Status", 100, "w"),
        ("created_at", "Created", 150, "w"),
    ]
    FILTERS = [("All roles", ""), ("Admin", "admin"), ("Manager", "manager"),
               ("Staff", "staff")]
    DEFAULT_FILTER = "All roles"
    SHOW_ARCHIVE = True
    EXTRA_ACTIONS = [("Reset password", "reset_password")]
    GLOBAL_ACTIONS = [("Change my password", "change_password")]
    TREE_HEIGHT = 15

    def load_rows(self) -> list[dict[str, Any]]:
        role = self.filter_value()
        rows = self.services.auth.list_users()
        result = []
        for row in rows:
            if role and row["role"] != role:
                continue
            if not self.include_archived_var.get() and not row["is_active"]:
                continue
            row["is_archived"] = not bool(row["is_active"])
            row["active"] = "Active" if row["is_active"] else "Deactivated"
            result.append(row)
        return result

    def row_tags(self, row: dict[str, Any]) -> list[str]:
        return ["archived"] if not row.get("is_active") else []

    def _fields(self, user: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        user = user or {}
        return [
            {"name": "username", "label": "Username", "kind": "entry",
             "value": user.get("username", "")},
            {"name": "full_name", "label": "Full name", "kind": "entry",
             "value": user.get("full_name", "")},
            {"name": "role", "label": "Role", "kind": "combo", "options": USER_ROLES,
             "value": user.get("role", "staff")},
            {"name": "password", "label": "Password", "kind": "password",
             "hint": "At least 6 characters with one number"},
            {"name": "confirm", "label": "Confirm password", "kind": "password"},
        ]

    def on_add(self) -> None:
        dialog = FormDialog(self, "Add user", self._fields(), on_save=self._create)
        if dialog.values is None:
            return
        self.refresh()

    def _create(self, values: dict[str, Any]) -> None:
        self.services.auth.create_user(
            username=values["username"], full_name=values["full_name"],
            role=values["role"], password=values["password"],
            confirm=values["confirm"])
        show_info(f"User {values['username']} was created.", self)

    def on_edit(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        dialog = FormDialog(
            self, f"Edit {row['username']}",
            [{"name": "full_name", "label": "Full name", "kind": "entry",
              "value": row["full_name"]},
             {"name": "role", "label": "Role", "kind": "combo", "options": USER_ROLES,
              "value": row["role"]}],
            columns=1, ok_text="Save",
            on_save=lambda values: self.services.auth.update_user(
                int(row["id"]), full_name=values["full_name"], role=values["role"]))
        if dialog.values is None:
            return
        self.refresh()

    def on_view(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        DetailDialog(self, f"User - {row['username']}",
                     [("Username", row["username"]),
                      ("Full name", row["full_name"]),
                      ("Role", row["role"]),
                      ("Status", row["active"]),
                      ("Created", row["created_at"])])

    def on_archive(self) -> None:
        """Reuse the archive button to activate/deactivate accounts."""
        row = self.selected_row()
        if row is None:
            return
        active = bool(row["is_active"])
        label = "deactivate" if active else "reactivate"
        if not confirm(f"Do you want to {label} the account '{row['username']}'?", self):
            return
        try:
            self.services.auth.update_user(int(row["id"]), is_active=not active)
        except Exception as exc:
            show_error(str(exc), self)
            return
        self.refresh()

    def on_reset_password(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        dialog = FormDialog(
            self, f"Reset password - {row['username']}",
            [{"name": "password", "label": "New password", "kind": "password"},
             {"name": "confirm", "label": "Confirm new password", "kind": "password"}],
            columns=1, ok_text="Reset password",
            on_save=lambda values: self.services.auth.reset_password(
                int(row["id"]), values["password"], values["confirm"]))
        if dialog.values is None:
            return
        show_info(f"The password for {row['username']} was changed.", self)

    def on_change_password(self) -> None:
        dialog = FormDialog(
            self, "Change my password",
            [{"name": "current", "label": "Current password", "kind": "password"},
             {"name": "password", "label": "New password", "kind": "password"},
             {"name": "confirm", "label": "Confirm new password", "kind": "password"}],
            columns=1, ok_text="Change password",
            on_save=lambda values: self.services.auth.change_password(
                self.user.id, values["current"], values["password"],
                values["confirm"]))
        if dialog.values is None:
            return
        show_info("Your password was changed.", self)
