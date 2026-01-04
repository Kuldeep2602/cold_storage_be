from rest_framework.permissions import BasePermission


class HasAssignedRole(BasePermission):
    """Block users who haven't been assigned a role yet"""
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role is not None)


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (getattr(user, 'role', None) == 'admin' or user.is_superuser))


class IsAdminOrOwner(BasePermission):
    """Only admin or owner can manage users and assign roles"""
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return getattr(user, 'role', None) in {'admin', 'owner'} or user.is_superuser


class IsManagerRole(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and getattr(user, 'role', None) == 'manager')


class IsOperatorRole(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and getattr(user, 'role', None) == 'operator')


class IsManagerOrAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return getattr(user, 'role', None) in {'manager', 'admin', 'owner'} or user.is_superuser


class IsOperatorOrHigher(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.role is None:  # Block unassigned users
            return False
        return getattr(user, 'role', None) in {'operator', 'manager', 'admin', 'owner'} or user.is_superuser


# Alias for IsManagerOrAdmin
IsManagerOrHigher = IsManagerOrAdmin

