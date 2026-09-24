from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from ury.ury.api import ury_kot_access


def frappe_stub(user, assignment=None):
	db = SimpleNamespace(exists=Mock(return_value=assignment))

	def throw(message, exception):
		raise exception(message)

	return SimpleNamespace(
		session=SimpleNamespace(user=user),
		db=db,
		throw=throw,
		PermissionError=frappe.PermissionError,
	), db


class TestURYKOTAccess(TestCase):
	def test_administrator_bypasses_pos_profile_assignment(self):
		stub, db = frappe_stub("Administrator")
		with patch.object(ury_kot_access, "frappe", stub):
			ury_kot_access.assert_pos_profile_access("Test POS Profile")
		db.exists.assert_not_called()

	def test_assigned_user_is_allowed(self):
		stub, db = frappe_stub("assigned@example.com", assignment="ROW-1")
		with patch.object(ury_kot_access, "frappe", stub):
			ury_kot_access.assert_pos_profile_access("Test POS Profile")
		db.exists.assert_called_once_with(
			"POS Profile User",
			{
				"parent": "Test POS Profile",
				"parenttype": "POS Profile",
				"parentfield": "applicable_for_users",
				"user": "assigned@example.com",
			},
		)

	def test_unassigned_user_is_denied(self):
		stub, _db = frappe_stub("unassigned@example.com")
		with (
			patch.object(ury_kot_access, "frappe", stub),
			patch.object(ury_kot_access, "_", side_effect=lambda message: message),
			self.assertRaises(frappe.PermissionError),
		):
			ury_kot_access.assert_pos_profile_access("Test POS Profile")

	def test_guest_is_denied_without_profile_lookup(self):
		stub, db = frappe_stub("Guest")
		with (
			patch.object(ury_kot_access, "frappe", stub),
			patch.object(ury_kot_access, "_", side_effect=lambda message: message),
			self.assertRaises(frappe.PermissionError),
		):
			ury_kot_access.assert_pos_profile_access("Test POS Profile")
		db.exists.assert_not_called()
