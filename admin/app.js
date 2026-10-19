"use strict";

const MIN_PASSWORD = 10;
const MAX_FILE = 2 * 1024 ** 3;
const $app = document.getElementById("app");
const state = { user: null };

const ICONS = {
  plus: '<path d="M12 5v14M5 12h14"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5M12 3v12"/>',
  copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  code: '<path d="M16 18l6-6-6-6M8 6l-6 6 6 6"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
  eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
  trash: '<path d="M3 6h18M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  replace: '<path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.5 9a9 9 0 0 1 14.9-3.4L23 10M1 14l4.6 4.4A9 9 0 0 0 20.5 15"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  folder: '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  back: '<path d="M15 18l-6-6 6-6"/>',
  close: '<path d="M18 6L6 18M6 6l12 12"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  dice: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1"/><circle cx="15.5" cy="15.5" r="1"/><circle cx="15.5" cy="8.5" r="1"/><circle cx="8.5" cy="15.5" r="1"/>',
};

function icon(name) {
  const span = document.createElement("span");
  span.style.display = "contents";
  span.innerHTML = `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
  return span.firstChild;
}

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key === "class") el.className = value;
    else if (key === "value") el.value = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.append(child.nodeType ? child : String(child));
  }
  return el;
}

function mount(...nodes) {
  $app.replaceChildren(...nodes);
}

function fmtSize(n) {
  if (n == null) return "";
  if (n < 1024) return `${n} Б`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} КБ`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} МБ`;
  return `${(n / 1024 ** 3).toFixed(2)} ГБ`;
}

function fmtDate(ts) {
  return new Date(ts * 1000).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
}

function plural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function errorText(data, status) {
  const detail = data && data.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  return `Ошибка сервера (${status})`;
}

async function api(method, path, body) {
  const options = { method, headers: {}, credentials: "same-origin" };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch("/api" + path, options);
  } catch {
    throw new ApiError("Нет связи с сервером", 0);
  }
  const data = (res.headers.get("content-type") || "").includes("json") ? await res.json() : null;
  if (res.status === 401 && path !== "/login" && path !== "/me") {
    state.user = null;
    renderLogin();
  }
  if (!res.ok) throw new ApiError(errorText(data, res.status), res.status);
  return data;
}

function uploadRequest(method, path, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, "/api" + path);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let data = null;
      try { data = JSON.parse(xhr.responseText); } catch {}
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new ApiError(errorText(data, xhr.status), xhr.status));
    };
    xhr.onerror = () => reject(new ApiError("Нет связи с сервером", 0));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

function toast(message, kind) {
  const el = h("div", { class: "toast" + (kind === "err" ? " err" : "") }, message);
  document.getElementById("toasts").append(el);
  setTimeout(() => el.remove(), kind === "err" ? 6000 : 2600);
}

function copyFallback(text) {
  const area = h("textarea", { readonly: true });
  area.value = text;
  area.style.position = "fixed";
  area.style.opacity = "0";
  (document.querySelector("dialog[open]") || document.body).append(area);
  area.select();
  const ok = document.execCommand("copy");
  area.remove();
  return ok;
}

async function copyText(text, what) {
  let ok = false;
  try {
    await navigator.clipboard.writeText(text);
    ok = true;
  } catch {
    ok = copyFallback(text);
  }
  if (ok) toast(`${what} скопирован${what.endsWith("а") ? "а" : ""}`);
  else toast("Не удалось скопировать, выделите и скопируйте вручную", "err");
}

function openDialog({ title, body, actions = [], wide = false }) {
  const dialog = h("dialog", { class: wide ? "wide" : "" },
    h("div", { class: "dialog-head" },
      h("h2", {}, title),
      h("button", { class: "btn ghost icon-only", type: "button", "aria-label": "Закрыть", onclick: () => dialog.close() }, icon("close"))),
    h("div", { class: "dialog-body" }, body),
    actions.length ? h("div", { class: "dialog-foot" }, actions) : null);
  dialog.addEventListener("close", () => dialog.remove());
  document.body.append(dialog);
  dialog.showModal();
  return dialog;
}

function confirmDialog(title, text, { okText = "Удалить", danger = true } = {}) {
  return new Promise((resolve) => {
    let result = false;
    const dialog = openDialog({
      title,
      body: h("p", { class: "muted" }, text),
      actions: [
        h("button", { class: "btn", type: "button", onclick: () => dialog.close() }, "Отмена"),
        h("button", { class: "btn " + (danger ? "danger-solid" : "primary"), type: "button",
          onclick: () => { result = true; dialog.close(); } }, okText),
      ],
    });
    dialog.addEventListener("close", () => resolve(result));
  });
}

function formDialog({ title, fields, submitText = "Сохранить", onSubmit }) {
  const error = h("p", { class: "form-error" });
  const submit = h("button", { class: "btn primary", type: "submit" }, submitText);
  const form = h("form", {}, fields, error,
    h("div", { class: "dialog-foot", style: null },
      h("button", { class: "btn", type: "button", onclick: () => dialog.close() }, "Отмена"), submit));
  const dialog = openDialog({ title, body: form });
  form.lastChild.style.margin = "18px -20px -18px";
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    error.textContent = "";
    submit.disabled = true;
    try {
      await onSubmit(form);
      dialog.close();
    } catch (err) {
      error.textContent = err.message;
    } finally {
      submit.disabled = false;
    }
  });
  const first = form.querySelector("input, textarea");
  if (first) first.focus();
  return dialog;
}

function field(label, input, hint) {
  return h("div", { class: "field" }, h("label", {}, label), input, hint ? h("div", { class: "hint" }, hint) : null);
}

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  try { localStorage.setItem("pd-theme", theme); } catch {}
}

function shell(active, ...content) {
  const themeBtn = h("button", {
    class: "btn ghost icon-only", type: "button",
    title: "Сменить тему", "aria-label": "Сменить тему",
    onclick: () => {
      setTheme(currentTheme() === "dark" ? "light" : "dark");
      themeBtn.replaceChildren(icon(currentTheme() === "dark" ? "sun" : "moon"));
    },
  }, icon(currentTheme() === "dark" ? "sun" : "moon"));

  return [
    h("header", { class: "topbar" },
      h("div", { class: "topbar-inner" },
        h("a", { class: "brand", href: "#/folders" }, h("span", { class: "brand-mark" }, "PDF"), h("span", {}, "PDF Display")),
        h("nav", { class: "nav" },
          h("a", { href: "#/folders", class: active === "folders" ? "active" : "" }, "Папки"),
          h("a", { href: "#/settings", class: active === "settings" ? "active" : "" }, "Настройки")),
        h("div", { class: "topbar-right" },
          h("span", { class: "user-name" }, state.user.username),
          themeBtn,
          h("button", { class: "btn ghost icon-only", type: "button", title: "Выйти", "aria-label": "Выйти", onclick: logout }, icon("logout"))))),
    h("main", { class: "container" }, ...content),
  ];
}

async function logout() {
  try { await api("POST", "/logout"); } catch {}
  state.user = null;
  location.hash = "";
  renderLogin();
}

function renderLogin() {
  document.title = "Вход — PDF Display";
  const error = h("p", { class: "form-error" });
  const username = h("input", { class: "input", name: "username", autocomplete: "username", required: true });
  const password = h("input", { class: "input", name: "password", type: "password", autocomplete: "current-password", required: true });
  const submit = h("button", { class: "btn primary", type: "submit" }, "Войти");
  const form = h("form", {
    class: "card login-card",
    onsubmit: async (e) => {
      e.preventDefault();
      error.textContent = "";
      submit.disabled = true;
      try {
        state.user = await api("POST", "/login", { username: username.value.trim(), password: password.value });
        route();
      } catch (err) {
        error.textContent = err.message;
        password.select();
      } finally {
        submit.disabled = false;
      }
    },
  },
    h("div", { class: "brand" }, h("span", { class: "brand-mark" }, "PDF"), h("span", {}, "PDF Display")),
    field("Логин", username),
    field("Пароль", password),
    error,
    submit);
  mount(h("div", { class: "login-wrap" }, form));
  username.focus();
}

function usageBlock(folder) {
  const quota = folder.quota_bytes;
  const ratio = quota ? Math.min(1, folder.used_bytes / quota) : 0;
  const bar = h("div");
  bar.style.width = `${(ratio * 100).toFixed(1)}%`;
  return h("div", { class: "usage" },
    h("div", { class: "usage-bar" + (ratio >= 0.95 ? " full" : "") }, bar),
    h("div", { class: "usage-text" },
      h("span", {}, quota ? `${fmtSize(folder.used_bytes)} из ${fmtSize(quota)}` : `${fmtSize(folder.used_bytes)}, без лимита`),
      h("span", {}, `${folder.file_count} ${plural(folder.file_count, "файл", "файла", "файлов")}`)));
}

function domainChips(folder) {
  if (!folder.domains.length) return h("div", { class: "chips" }, h("span", { class: "chip warn" }, "Нет разрешённых сайтов"));
  return h("div", { class: "chips" }, folder.domains.map((d) => h("span", { class: "chip" }, d)));
}

async function renderFolders() {
  document.title = "Папки — PDF Display";
  const list = h("div", { class: "folders" });
  mount(...shell("folders",
    h("div", { class: "page-head" },
      h("h1", {}, "Папки"),
      h("div", { class: "spacer" }),
      h("button", { class: "btn primary", type: "button", onclick: () => folderDialog() }, icon("plus"), "Новая папка")),
    list));

  const folders = await api("GET", "/folders");
  if (!folders.length) {
    list.replaceWith(h("div", { class: "card empty" }, icon("folder"),
      h("p", {}, "Папок пока нет. Создайте папку для первого сайта клиента.")));
    return;
  }
  list.replaceChildren(...folders.map((f) =>
    h("a", { class: "card folder-card", href: `#/folders/${f.id}` },
      h("div", { class: "folder-title" }, icon("folder"), h("h2", {}, f.name)),
      domainChips(f),
      usageBlock(f))));
}

function folderDialog(folder) {
  const editing = Boolean(folder);
  const name = h("input", { class: "input", name: "name", required: true, maxlength: 200, value: folder ? folder.name : "",
    placeholder: "сайт.клиент.md" });
  const domains = h("textarea", { class: "input", name: "domains", rows: 3, placeholder: "сайт.клиент.md" });
  domains.value = folder ? folder.domains.join("\n") : "";
  const quota = h("input", { class: "input", name: "quota", type: "number", min: "0.001", step: "any",
    value: folder && folder.quota_bytes ? +(folder.quota_bytes / 1024 ** 3).toFixed(3) : "", placeholder: "например, 20" });
  const direct = h("input", { type: "checkbox", name: "direct" });
  direct.checked = folder ? folder.allow_direct : false;

  let domainsTouched = editing;
  domains.addEventListener("input", () => { domainsTouched = true; });
  name.addEventListener("input", () => { if (!domainsTouched) domains.value = name.value.trim(); });

  formDialog({
    title: editing ? "Настройки папки" : "Новая папка",
    submitText: editing ? "Сохранить" : "Создать",
    fields: [
      field("Название", name, "Обычно — адрес сайта клиента."),
      field("Сайты, где можно показывать файлы", domains,
        "По одному на строку. Вариант с www добавляется автоматически. Пусто — документы не покажутся нигде."),
      field("Лимит места, ГБ", quota, "Пусто — без лимита."),
      h("label", { class: "check" }, direct,
        h("span", {}, "Разрешить открывать ссылку напрямую", h("br"),
          h("span", { class: "muted small" }, "По умолчанию документ виден только внутри iframe на разрешённых сайтах."))),
    ],
    onSubmit: async () => {
      const body = {
        name: name.value.trim(),
        domains: domains.value.split(/[\s,]+/).map((d) => d.trim()).filter(Boolean),
        quota_gb: quota.value ? Number(quota.value) : null,
        allow_direct: direct.checked,
      };
      if (editing) {
        await api("PATCH", `/folders/${folder.id}`, body);
        toast("Папка сохранена");
        renderFolder(folder.id);
      } else {
        const created = await api("POST", "/folders", body);
        toast("Папка создана");
        location.hash = `#/folders/${created.id}`;
      }
    },
  });
}

async function deleteFolder(folder) {
  const text = folder.file_count
    ? `Папка «${folder.name}» и ${folder.file_count} ${plural(folder.file_count, "файл", "файла", "файлов")} в ней будут удалены без возможности восстановления. Документы перестанут показываться на сайте.`
    : `Папка «${folder.name}» будет удалена.`;
  if (!(await confirmDialog("Удалить папку?", text))) return;
  try {
    await api("DELETE", `/folders/${folder.id}?force=${folder.file_count ? "true" : "false"}`);
    toast("Папка удалена");
    location.hash = "#/folders";
  } catch (err) {
    toast(err.message, "err");
  }
}

async function renderFolder(folderId) {
  const [folder, files] = await Promise.all([api("GET", `/folders/${folderId}`), api("GET", `/files?folder_id=${folderId}`)]);
  document.title = `${folder.name} — PDF Display`;

  const fileInput = h("input", { type: "file", accept: "application/pdf,.pdf", multiple: true, hidden: true });
  const uploads = h("div", { class: "uploads" });
  const dropzone = h("div", { class: "dropzone", role: "button", tabindex: "0", onclick: () => fileInput.click(),
    onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } } },
    icon("upload"),
    h("div", {}, h("strong", {}, "Перетащите PDF сюда"), " или нажмите, чтобы выбрать файлы"),
    h("div", { class: "small" }, "До 2 ГБ на файл"));

  let pending = 0;
  const startUploads = (fileList) => {
    for (const file of fileList) {
      pending++;
      uploadOne(folder, file, uploads).finally(() => {
        if (--pending === 0) renderFolder(folderId);
      });
    }
  };
  fileInput.addEventListener("change", () => { startUploads(fileInput.files); fileInput.value = ""; });
  dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("over"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("over"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("over");
    startUploads(e.dataTransfer.files);
  });

  const listBox = h("div", { class: "file-list" });
  const search = h("input", { class: "input", type: "search", placeholder: "Поиск по имени" });
  const drawList = () => {
    const q = search.value.trim().toLowerCase();
    const shown = q ? files.filter((f) => f.name.toLowerCase().includes(q)) : files;
    if (!shown.length) {
      listBox.replaceChildren(h("div", { class: "empty" }, icon("file"),
        h("p", {}, files.length ? "Ничего не найдено" : "В папке пока нет файлов")));
      return;
    }
    listBox.replaceChildren(...shown.map((f) => fileRow(f, folderId)));
  };
  search.addEventListener("input", drawList);
  drawList();

  mount(...shell("folders",
    h("a", { class: "back", href: "#/folders" }, icon("back"), "Все папки"),
    h("div", { class: "card folder-head" },
      h("div", { class: "info" },
        h("h1", {}, folder.name),
        domainChips(folder),
        folder.allow_direct ? h("div", { class: "chips", style: null }, h("span", { class: "chip warn" }, "Прямые ссылки разрешены")) : null,
        usageBlock(folder)),
      h("div", { class: "actions" },
        h("button", { class: "btn", type: "button", onclick: () => folderDialog(folder) }, icon("edit"), "Изменить"),
        h("button", { class: "btn danger", type: "button", onclick: () => deleteFolder(folder) }, icon("trash"), "Удалить"))),
    dropzone, fileInput, uploads,
    h("div", { class: "files-head" }, h("h2", {}, "Файлы"), h("span", { class: "muted small" }, String(files.length)), search),
    listBox));
}

async function uploadOne(folder, file, uploads) {
  const bar = h("div");
  const status = h("span", { class: "status" }, "0%");
  const row = h("div", { class: "upload-row" }, h("span", { class: "name" }, file.name), status, h("div", { class: "usage-bar" }, bar));
  uploads.prepend(row);
  const fail = (message) => {
    status.textContent = message;
    status.className = "status err";
    bar.style.width = "0";
  };
  if (!/\.pdf$/i.test(file.name) && file.type !== "application/pdf") return fail("Это не PDF");
  if (file.size > MAX_FILE) return fail("Больше 2 ГБ");
  try {
    await uploadRequest("POST", `/folders/${folder.id}/files`, file, (p) => {
      bar.style.width = `${(p * 100).toFixed(0)}%`;
      status.textContent = p < 1 ? `${(p * 100).toFixed(0)}%` : "Обработка…";
    });
    status.textContent = "Загружен";
    status.className = "status ok";
  } catch (err) {
    fail(err.message);
    toast(`${file.name}: ${err.message}`, "err");
  }
}

function fileRow(file, folderId) {
  const act = (iconName, label, onclick, extra = "") =>
    h("button", { class: `btn ghost sm ${extra}`, type: "button", title: label, onclick }, icon(iconName), h("span", {}, label));
  return h("div", { class: "file-row" },
    h("div", { class: "file-icon" }, "PDF"),
    h("div", { class: "file-main" },
      h("div", { class: "file-name", title: file.name }, file.name),
      h("div", { class: "file-meta" }, `${fmtSize(file.size)} · ${fmtDate(file.updated_at)}`)),
    h("div", { class: "file-actions" },
      act("code", "Код iframe", () => embedDialog(file)),
      act("eye", "Просмотр", () => previewDialog(file)),
      act("replace", "Заменить", () => replaceFile(file, folderId)),
      act("edit", "Переименовать", () => renameDialog(file, folderId)),
      act("trash", "Удалить", () => deleteFile(file, folderId), "danger")));
}

function embedDialog(file) {
  const code = h("textarea", { class: "input mono code-box", readonly: true });
  code.value = file.embed_html;
  const link = h("input", { class: "input mono", readonly: true, value: file.view_url });
  openDialog({
    title: file.name,
    body: [
      field("Код для сайта", code, "Вставьте его в страницу на разрешённом сайте."),
      h("div", { class: "input-row" }, h("button", { class: "btn primary", type: "button", onclick: () => copyText(file.embed_html, "Код") }, icon("copy"), "Скопировать код")),
      h("div", { style: null }, h("br")),
      field("Ссылка", link),
      h("div", { class: "input-row" }, h("button", { class: "btn", type: "button", onclick: () => copyText(file.view_url, "Ссылка") }, icon("link"), "Скопировать ссылку")),
    ],
  });
  code.addEventListener("focus", () => code.select());
}

function previewDialog(file) {
  const frame = h("iframe", { class: "preview-frame", src: `/v/${file.id}`, title: file.name });
  const dialog = openDialog({ title: file.name, body: frame, wide: true });
  dialog.querySelector(".dialog-body").style.padding = "0";
}

function replaceFile(file, folderId) {
  const input = h("input", { type: "file", accept: "application/pdf,.pdf" });
  input.addEventListener("change", async () => {
    const newFile = input.files[0];
    if (!newFile) return;
    if (!(await confirmDialog("Заменить файл?",
      `«${file.name}» будет заменён на «${newFile.name}». Ссылка и код iframe останутся прежними, на сайтах сразу будет новая версия.`,
      { okText: "Заменить", danger: false }))) return;
    toast("Загрузка…");
    try {
      await uploadRequest("PUT", `/files/${file.id}`, newFile, () => {});
      toast("Файл заменён");
      renderFolder(folderId);
    } catch (err) {
      toast(err.message, "err");
    }
  });
  input.click();
}

function renameDialog(file, folderId) {
  const name = h("input", { class: "input", name: "name", required: true, maxlength: 255, value: file.name });
  formDialog({
    title: "Переименовать",
    fields: [field("Имя файла", name, "Видно в просмотрщике и при скачивании.")],
    onSubmit: async () => {
      await api("PATCH", `/files/${file.id}`, { name: name.value.trim() });
      toast("Имя изменено");
      renderFolder(folderId);
    },
  });
}

async function deleteFile(file, folderId) {
  if (!(await confirmDialog("Удалить файл?",
    `«${file.name}» будет удалён без возможности восстановления. На сайтах вместо документа появится «Документ не найден».`))) return;
  try {
    await api("DELETE", `/files/${file.id}`);
    toast("Файл удалён");
    renderFolder(folderId);
  } catch (err) {
    toast(err.message, "err");
  }
}

function generatePassword(length = 20) {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%&*-_=+?";
  const limit = 256 - (256 % alphabet.length);
  let out = "";
  while (out.length < length) {
    for (const b of crypto.getRandomValues(new Uint8Array(length * 2))) {
      if (b < limit && out.length < length) out += alphabet[b % alphabet.length];
    }
  }
  return out;
}

function passwordScore(pw) {
  if (!pw) return 0;
  const classes = [/[a-zа-яё]/, /[A-ZА-ЯЁ]/, /\d/, /[^\da-zA-Zа-яА-ЯёЁ]/].filter((re) => re.test(pw)).length;
  if (pw.length < MIN_PASSWORD) return 1;
  if (pw.length >= 16 && classes >= 3) return 4;
  if (pw.length >= 12 && classes >= 3) return 3;
  return 2;
}

function usernameCard() {
  const newName = h("input", { class: "input", autocomplete: "username", required: true, minlength: 3, maxlength: 64,
    pattern: "[A-Za-z0-9._@\\-]{3,64}", value: state.user.username });
  const password = h("input", { class: "input", type: "password", autocomplete: "current-password", required: true });
  const error = h("p", { class: "form-error" });
  const submit = h("button", { class: "btn primary", type: "submit" }, "Сменить логин");
  return h("form", {
    class: "card",
    onsubmit: async (e) => {
      e.preventDefault();
      error.textContent = "";
      submit.disabled = true;
      try {
        const res = await api("POST", "/me/username", { current_password: password.value, new_username: newName.value.trim() });
        state.user.username = res.username;
        toast(`Логин изменён на ${res.username}`);
        renderSettings();
      } catch (err) {
        error.textContent = err.message;
      } finally {
        submit.disabled = false;
      }
    },
  },
    h("h2", {}, "Логин"),
    field("Новый логин", newName, "От 3 до 64 символов: латинские буквы, цифры и . _ @ -"),
    field("Текущий пароль", password, "Для подтверждения."),
    error,
    submit);
}

function renderSettings() {
  document.title = "Настройки — PDF Display";

  const current = h("input", { class: "input", type: "password", autocomplete: "current-password", required: true });
  const next = h("input", { class: "input", type: "password", autocomplete: "new-password", required: true, minlength: MIN_PASSWORD });
  const repeat = h("input", { class: "input", type: "password", autocomplete: "new-password", required: true });
  const meterBar = h("div");
  const meterText = h("div", { class: "hint" }, `Минимум ${MIN_PASSWORD} символов.`);
  const error = h("p", { class: "form-error" });
  const submit = h("button", { class: "btn primary", type: "submit" }, "Сменить пароль");

  const updateMeter = () => {
    const score = passwordScore(next.value);
    const levels = [
      [0, "var(--bar)", `Минимум ${MIN_PASSWORD} символов.`],
      [25, "var(--danger)", `Слишком короткий: ${next.value.length} из ${MIN_PASSWORD}.`],
      [50, "#e0a200", "Слабый: добавьте длину, заглавные буквы, цифры и символы."],
      [75, "var(--accent)", "Неплохо. Ещё лучше — 16 символов и больше."],
      [100, "var(--success)", "Надёжный пароль."],
    ];
    const [width, color, text] = levels[score];
    meterBar.style.width = `${width}%`;
    meterBar.style.background = color;
    meterText.textContent = text;
  };
  next.addEventListener("input", updateMeter);

  const show = (visible) => { next.type = repeat.type = visible ? "text" : "password"; };
  const generate = () => {
    const pw = generatePassword();
    next.value = repeat.value = pw;
    show(true);
    updateMeter();
    copyText(pw, "Пароль");
  };

  const form = h("form", {
    class: "card",
    onsubmit: async (e) => {
      e.preventDefault();
      error.textContent = "";
      if (next.value.length < MIN_PASSWORD) { error.textContent = `Пароль должен быть не короче ${MIN_PASSWORD} символов`; return; }
      if (next.value !== repeat.value) { error.textContent = "Пароли не совпадают"; return; }
      submit.disabled = true;
      try {
        await api("POST", "/me/password", { current_password: current.value, new_password: next.value });
        form.reset();
        show(false);
        updateMeter();
        toast("Пароль изменён. Другие устройства разлогинены.");
      } catch (err) {
        error.textContent = err.message;
      } finally {
        submit.disabled = false;
      }
    },
  },
    h("h2", {}, "Смена пароля"),
    h("div", { class: "notice" }, icon("shield"),
      h("div", {},
        h("strong", {}, "Пароль должен быть сложным и длинным. "),
        "Система доступна из интернета, и кто угодно может пытаться подобрать пароль. " +
        "Лучше всего нажать «Сгенерировать» и сохранить пароль в менеджере паролей.")),
    field("Текущий пароль", current),
    h("div", { class: "field" },
      h("label", {}, "Новый пароль"),
      h("div", { class: "input-row" }, next,
        h("button", { class: "btn", type: "button", onclick: generate, title: "Сгенерировать и скопировать" }, icon("dice"), "Сгенерировать")),
      h("div", { class: "pw-meter" }, meterBar),
      meterText),
    field("Повторите новый пароль", repeat),
    error,
    submit);

  const themeButtons = h("div", { class: "segmented" });
  const drawTheme = () => {
    const theme = currentTheme();
    themeButtons.replaceChildren(
      h("button", { type: "button", class: theme === "light" ? "active" : "", onclick: () => { setTheme("light"); drawTheme(); } }, icon("sun"), "Светлая"),
      h("button", { type: "button", class: theme === "dark" ? "active" : "", onclick: () => { setTheme("dark"); drawTheme(); } }, icon("moon"), "Тёмная"));
  };
  drawTheme();

  mount(...shell("settings",
    h("div", { class: "page-head" }, h("h1", {}, "Настройки")),
    h("div", { class: "settings" },
      usernameCard(),
      form,
      h("div", { class: "card" },
        h("h2", {}, "Тема"),
        themeButtons,
        h("p", { class: "muted small" }, "Сохраняется только в этом браузере на этом устройстве. Другие пользователи и устройства не затрагиваются.")))));
}

async function route() {
  if (!state.user) {
    try {
      state.user = await api("GET", "/me");
    } catch {
      renderLogin();
      return;
    }
  }
  const hash = location.hash || "#/folders";
  const match = hash.match(/^#\/folders\/(\d+)$/);
  try {
    if (match) await renderFolder(Number(match[1]));
    else if (hash === "#/settings") renderSettings();
    else await renderFolders();
  } catch (err) {
    if (err.status === 401) return;
    if (err.status === 404) {
      toast(err.message, "err");
      location.hash = "#/folders";
      return;
    }
    toast(err.message, "err");
  }
}

window.addEventListener("hashchange", route);
route();
