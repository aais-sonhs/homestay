"""Abstract model helpers for new Homestay applications.

Existing models keep their current deletion fields and database tables. New
applications can inherit these helpers without duplicating soft-delete logic.
"""

from django.db import models


class SoftDeleteQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_deleted=False)

    def deleted(self):
        return self.filter(is_deleted=True)

    def soft_delete(self):
        return self.active().update(is_deleted=True)

    def hard_delete(self):
        return super().delete()


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    def get_queryset(self):
        return super().get_queryset().active()


class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False, db_index=True)

    objects = SoftDeleteManager()
    all_objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        if self.is_deleted:
            return 0, {self._meta.label: 0}
        self.is_deleted = True
        self.save(using=using, update_fields=["is_deleted"])
        return 1, {self._meta.label: 1}

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

