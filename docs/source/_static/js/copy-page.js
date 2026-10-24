// Wires the page actions to the Markdown copy of the page that sphinx-llm links in <head>.
(function () {
    const link = document.querySelector('link[rel="alternate"][type="text/markdown"]');
    const actions = document.querySelector('.page-actions');
    if (!link || !actions) {
        return;
    }

    const markdownUrl = new URL(link.getAttribute('href'), location.href).href;
    const question = encodeURIComponent(`Read ${markdownUrl} so I can ask questions about it.`);
    actions.querySelector('.view-markdown').href = markdownUrl;
    actions.querySelector('.open-chatgpt').href = `https://chatgpt.com/?q=${question}`;
    actions.querySelector('.open-claude').href = `https://claude.ai/new?q=${question}`;

    // Safari writes to the clipboard only synchronously inside the click, so the fetch is handed over as a promise.
    let markdown = null;
    function fetchMarkdown() {
        markdown ??= fetch(markdownUrl).then((response) => (response.ok ? response.text() : Promise.reject(response.status)));
        return markdown;
    }

    const button = actions.querySelector('.copy-page');
    const label = button.querySelector('span');
    button.addEventListener('click', () => {
        const blob = fetchMarkdown().then((text) => new Blob([text], {type: 'text/plain'}));
        navigator.clipboard.write([new ClipboardItem({'text/plain': blob})]).then(
            () => {
                label.textContent = 'Copied';
                setTimeout(() => { label.textContent = 'Copy page'; }, 2000);
            },
            () => { window.open(markdownUrl, '_blank', 'noopener'); },
        );
    });

    actions.hidden = false;
})();
