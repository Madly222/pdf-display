// Настройка PDF.js до старта просмотрщика. Страница /v/<id> показывает файл /f/<id>,
// страница /r/<ticket> (просмотр из Odoo) — сконвертированный PDF /r/<ticket>/file.
// Событие webviewerloaded уходит в документ родителя, если тот с того же домена,
// иначе в собственный документ, поэтому слушаем оба.
(function () {
  var path = location.pathname;
  var fileUrl;
  var m = path.match(/^\/v\/([a-z0-9]+)$/);
  if (m) fileUrl = "/f/" + m[1];
  m = path.match(/^\/r\/([A-Za-z0-9_-]+)$/);
  if (m) fileUrl = "/r/" + m[1] + "/file";
  if (!fileUrl) return;

  function setup(e) {
    if (e.detail && e.detail.source !== window) return;
    var o = window.PDFViewerApplicationOptions;
    o.set("disablePreferences", true);
    o.set("defaultUrl", fileUrl);
    o.set("annotationEditorMode", -1);
    o.set("disableHistory", true);
    // Миниатюры страниц не открываем сами: в узком iframe они закрывают документ.
    o.set("sidebarViewOnLoad", 0);
  }

  document.addEventListener("webviewerloaded", setup);
  try {
    if (parent !== window) parent.document.addEventListener("webviewerloaded", setup);
  } catch (e) {}
})();
