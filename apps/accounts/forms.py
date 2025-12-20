import re

from django import forms
from django.contrib.auth import get_user_model

from .models import Customer

User = get_user_model()

def format_phone_number(phone_raw):
    """Приводит номер к формату: +7 (999) 999-99-99"""
    if not phone_raw: 
        return ""
    
    # Оставляем только цифры
    digits = re.sub(r'\D', '', str(phone_raw))

    # Обработка длины и кода страны
    if len(digits) == 11:
        if digits.startswith('8'):
            digits = '7' + digits[1:] 
        elif not digits.startswith('7'):
             raise forms.ValidationError('Номер должен начинаться с +7 или 8.')
    elif len(digits) == 10:
        digits = '7' + digits 
    else:
        raise forms.ValidationError('Некорректная длина номера.')

    # Формируем итоговую строку: +7 (XXX) XXX-XX-XX
    return f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"

class LoginForm(forms.ModelForm):
    """Проверяет существование пользователя и корректность пароля"""
    password = forms.CharField(widget = forms.PasswordInput)

    class Meta:
        model = User
        fields = ['username', 'password']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Логин'
        self.fields['password'].label = 'Пароль'

    def clean(self):
        username = self.cleaned_data['username']
        password = self.cleaned_data['password']
        
        user = User.objects.filter(username = username).first()
        if not user:
            raise forms.ValidationError(f'Пользователь с логином {username} не найден в системе.')
        if not user.check_password(password):
            raise forms.ValidationError('Неправильный пароль. Попробуйте еще раз.')
        return self.cleaned_data
    
class RegistrationForm(forms.ModelForm):
    """Отображает форму регистрации с полями для создания нового пользователя"""
    password = forms.CharField(widget = forms.PasswordInput)
    confirm_password = forms.CharField(widget = forms.PasswordInput)
    phone = forms.CharField(required = True, label = 'Номер телефона')
    email = forms.EmailField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Логин'
        self.fields['password'].label = 'Пароль'
        self.fields['confirm_password'].label = 'Подтвердите пароль'
        self.fields['phone'].label = 'Номер телефона'
        self.fields['email'].label = 'Электронная почта'
        self.fields['first_name'].label = 'Имя'
        self.fields['last_name'].label = 'Фамилия'
        
    def clean_email(self):
        email = self.cleaned_data['email']
        disposable_domains = ['mailinator.com', 'tempmail.com', '10minutemail.com'] 
        domain = email.split('@')[-1]
        local_part = email.split('@')[0]

        if domain in disposable_domains:
            raise forms.ValidationError('Использование временных email-адресов запрещено.')
        if any(char in local_part for char in ['!', '#', '$', '%', '^', '&', '*']):
            raise forms.ValidationError('Локальная часть email содержит запрещенные символы.')
        if User.objects.filter(email = email).exists():
            raise forms.ValidationError(f'Пользователь с почтой {email} уже существует.')
        return email
    
    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username = username).exists():
            raise forms.ValidationError(f'Имя {username} уже занято. Попробуйте другое.')
        return username
    
    def clean_phone(self):
        phone = self.cleaned_data['phone']
        formatted_phone = format_phone_number(phone)
        
        if Customer.objects.filter(phone=formatted_phone).exists():
             raise forms.ValidationError('Пользователь с таким телефоном уже существует.')
             
        return formatted_phone
    
    def clean(self):
        password = self.cleaned_data['password']
        confirm_password = self.cleaned_data['confirm_password']
        if password != confirm_password:
            raise forms.ValidationError('Пароли не совпадают.')
        return self.cleaned_data

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'password', 'confirm_password']

class ProfileEditForm(forms.ModelForm):
    phone = forms.CharField(max_length=25, required=False, label='Телефон')
    address = forms.CharField(max_length=255, required=False, label='Адрес')
    first_name = forms.CharField(max_length=150, required=False, label="Имя")
    last_name = forms.CharField(max_length=150, required=False, label="Фамилия")

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']

    def __init__(self, *args, **kwargs):
        self.customer = kwargs.pop('customer', None)
        super().__init__(*args, **kwargs)

        common_classes = (
            "w-full px-4 py-2 text-sm rounded-lg border outline-none transition-all duration-200 "
            
            "disabled:opacity-100"
            
            # --- 1. СТИЛЬ РЕДАКТИРОВАНИЯ (БАЗОВЫЙ) ---
            "bg-white text-gray-900 border-gray-200 cursor-text "
            
            # --- 2. СТИЛЬ ПРОСМОТРА (ЗАБЛОКИРОВАНО) ---
            "disabled:bg-gray-50 disabled:border-gray-100 disabled:cursor-not-allowed "
            
            "focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20"
        )

        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = common_classes
            field.widget.attrs['placeholder'] = field.label

        if self.customer:
            self.fields['phone'].initial = self.customer.phone
            self.fields['address'].initial = self.customer.address

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if not phone:
            return ""
        return format_phone_number(phone)

    def save(self, commit=True):
        user = super().save(commit=commit)
        if self.customer:
            self.customer.phone = self.cleaned_data['phone']
            self.customer.address = self.cleaned_data['address']
            if commit:
                self.customer.save()
        return user