document.addEventListener('DOMContentLoaded', function() {
    const viewer = toastui.Editor.factory({
        el: document.querySelector('#viewer'),
        viewer: true,
        initialValue: `{{ article.current_revision.content|default:""}}`  // Markdown original, pas le HTML déjà rendu
    });
});