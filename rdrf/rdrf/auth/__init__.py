def is_user_privileged(user):
    return not (user.is_patient or user.is_parent or user.is_carrier)
