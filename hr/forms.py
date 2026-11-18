import re

from django import forms

from .models import Employee, PayrollDetails


def date_input():
    return forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


class EmployeeForm(forms.ModelForm):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput, initial=0)

    class Meta:
        model = Employee
        fields = ("number", "first_name", "last_name", "work_email", "work_phone", "job_title",
                  "department", "start_date", "end_date", "is_active")
        widgets = {"start_date": date_input(), "end_date": date_input()}

    def clean(self):
        values = super().clean()
        start, end = values.get("start_date"), values.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "La date de sortie doit suivre la date d’entrée.")
        return values


class PayrollForm(forms.ModelForm):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput, initial=0)
    iban = forms.CharField(label="IBAN de versement", max_length=50, required=False)

    class Meta:
        model = PayrollDetails
        fields = ("gross_amount", "frequency", "work_percentage", "effective_date", "iban")
        widgets = {"effective_date": date_input()}

    def clean_iban(self):
        iban = "".join(self.cleaned_data["iban"].upper().split())
        if not iban:
            return ""
        if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", iban):
            raise forms.ValidationError("Renseignez un IBAN valide.")
        rearranged = iban[4:] + iban[:4]
        if int("".join(char if char.isdigit() else str(ord(char) - 55) for char in rearranged)) % 97 != 1:
            raise forms.ValidationError("La clé de contrôle de l’IBAN est invalide.")
        return iban
