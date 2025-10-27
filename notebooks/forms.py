from django import forms
from .models import NotebookMeta


class NotebookUploadForm(forms.ModelForm):
    """Formulaire d'upload de notebook avec options de traitement."""
    
    sandbox_mode = forms.ChoiceField(
        choices=[
            ('strict', 'Strict (lecture seule)'),
            ('temp', 'Temporaire (isolé)'),
            ('none', 'Aucun (développement)'),
        ],
        initial='temp',
        required=True,
        widget=forms.RadioSelect,
        help_text="Mode d'exécution du notebook"
    )
    
    create_wiki_article = forms.BooleanField(
        initial=True,
        required=False,
        label="Créer un article wiki",
        help_text="Génère automatiquement une page de documentation"
    )
    
    class Meta:
        model = NotebookMeta
        fields = ['name', 'file']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom du notebook'
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.ipynb'
            }),
        }
        help_texts = {
            'name': 'Nom descriptif pour identifier le notebook',
            'file': 'Fichier .ipynb à uploader',
        }
    
    def clean_file(self):
        """Valide que le fichier est bien un notebook Jupyter."""
        file = self.cleaned_data.get('file')
        
        if not file:
            return file
        
        # Vérification de l'extension
        if not file.name.endswith('.ipynb'):
            raise forms.ValidationError(
                "Le fichier doit être un notebook Jupyter (.ipynb)"
            )
        
        # Vérification de la taille (max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB
        if file.size > max_size:
            raise forms.ValidationError(
                f"Le fichier est trop volumineux (max {max_size // 1024 // 1024}MB)"
            )
        
        return file
    
    def clean_name(self):
        """Nettoie et valide le nom du notebook."""
        name = self.cleaned_data.get('name')
        
        if not name:
            # Génère un nom à partir du fichier
            file = self.cleaned_data.get('file')
            if file:
                name = file.name.replace('.ipynb', '').replace('_', ' ').title()
        
        return name