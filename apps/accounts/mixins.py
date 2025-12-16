from django import views

from apps.accounts.models import Customer, Notifications

class NotificationsMixin(views.generic.detail.SingleObjectMixin, views.View):
    @staticmethod
    def notifications(user):
        # Возвращает непрочитанные уведомления для пользователя
        if user.is_authenticated:
            return Notifications.objects.unread_for_recipient(user.customer)
        return Notifications.objects.none()
    
    def get_context_data(self, **kwargs):
        # Добавляет уведомления в контекст шаблона
        context = super().get_context_data(**kwargs)
        context['notifications'] = self.notifications(self.request.user)
        return context