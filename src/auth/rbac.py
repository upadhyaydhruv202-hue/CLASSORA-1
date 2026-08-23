"""Roles: existing teacher/student plus optional institutional staff roles."""

EXISTING_ROLES = ("teacher", "student")
STAFF_ROLES = ("administrator", "counsellor", "faculty", "mentor")
MERCHANT_ROLES = ("merchant",)
ALL_ROLES = EXISTING_ROLES + STAFF_ROLES + MERCHANT_ROLES

ROLE_PERMISSIONS = {
    "teacher": {
        "view": ["own_subjects", "enrolled_students", "attendance_logs", "institution_dashboard", "login_history", "success_hub", "own_complaints", "institutional_anomalies", "institutional_dropout", "rewards", "predictions"],
        "create": ["subjects", "attendance_sessions", "teacher_invites", "complaints", "reward_awards", "secure_attendance", "prediction_documents"],
        "edit": ["own_password"],
        "delete": ["not_applicable"],
        "manage": ["own_subjects", "attendance_confirm", "institutional_anomalies", "institutional_dropout"],
        "export": ["attendance_records"],
        "access": ["teacher_dashboard", "face_attendance", "voice_attendance"],
    },
    "student": {
        "view": ["own_subjects", "own_attendance", "own_success_snapshot", "own_mentorship", "own_account_status", "own_rewards", "own_predictions", "communities"],
        "create": ["self_enrollment", "help_request", "mentorship_request", "mentorship_feedback", "appeals", "reward_submissions", "reward_claims", "attendance_verification", "prediction_documents", "community_requests", "community_posts"],
        "edit": ["own_tasks", "own_mentorship_messages"],
        "delete": ["own_enrollment"],
        "manage": [],
        "export": [],
        "access": ["student_dashboard", "face_login", "anonymous_mentorship"],
    },
    "administrator": {
        "view": ["institution_dashboard", "success_hub", "audit", "health", "settings", "mentorship_admin", "complaints", "complaint_evidence", "appeals", "institutional_anomalies", "institutional_dropout", "rewards", "predictions", "communities"],
        "create": ["staff_invites", "reward_policies", "reward_merchants", "reward_offers", "prediction_documents", "community_categories"],
        "edit": ["settings", "anomaly_settings", "dropout_settings", "reward_settings", "attendance_settings", "prediction_settings", "community_settings"],
        "manage": ["permissions", "mentorship_suspend", "complaint_review", "student_status", "bans", "appeals", "institutional_anomalies", "institutional_dropout", "rewards", "predictions", "communities"],
        "export": ["reports", "reward_reports"],
        "access": ["admin_dashboard", "complaint_management", "execute_ban"],
    },
    "counsellor": {
        "view": ["success_hub", "student_360", "cases", "mentorship_assign", "own_complaints", "institutional_anomalies", "rewards", "predictions"],
        "create": ["interventions", "appointments", "anonymous_mentorship", "complaints", "reward_awards", "prediction_documents"],
        "edit": ["cases", "recommendations"],
        "manage": ["caseload"],
        "access": ["counsellor_dashboard"],
    },
    "faculty": {
        "view": ["course_students", "faculty_portal", "anonymous_mentorship", "own_complaints", "rewards", "predictions"],
        "create": ["referrals", "notes", "mentorship_messages", "complaints", "reward_awards", "prediction_documents"],
        "access": ["faculty_dashboard"],
        "manage": [],
    },
    "mentor": {
        "view": ["assigned_students", "anonymous_mentorship", "own_complaints", "rewards", "predictions"],
        "create": ["mentor_notes", "mentorship_messages", "complaints", "reward_awards", "prediction_documents"],
        "access": ["mentor_dashboard"],
        "manage": [],
    },
    "merchant": {
        "view": ["own_merchant_vouchers"],
        "create": [],
        "manage": ["own_redemptions"],
        "access": ["merchant_dashboard"],
    },
}


def current_role(session_state) -> str | None:
    role = session_state.get("user_role")
    if role in ALL_ROLES and session_state.get("is_logged_in"):
        return role
    return None


def has_role(session_state, *roles: str) -> bool:
    role = current_role(session_state)
    return role is not None and role in roles


def can(session_state, action: str, resource: str) -> bool:
    role = current_role(session_state)
    if not role:
        return False
    return resource in ROLE_PERMISSIONS.get(role, {}).get(action, [])
