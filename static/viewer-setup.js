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
    o.set("sidebarViewOnLoad", 0);
  }

  document.addEventListener("webviewerloaded", setup);
  try {
    if (parent !== window) parent.document.addEventListener("webviewerloaded", setup);
  } catch (e) {}
})();
