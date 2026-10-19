import { Attachment } from "@mail/core/common/attachment_model";
import { FileModel } from "@web/core/file_viewer/file_model";
import { patch } from "@web/core/utils/patch";

const SHEET_EXT = new Set(["xls", "xlsx", "xlsm", "xlsb", "xlt", "xltx", "ods", "ots", "csv"]);
const DOC_EXT = new Set([
    "doc", "docx", "docm", "dot", "dotx", "odt", "ott", "rtf", "wpd", "wps",
    "ppt", "pptx", "pptm", "pps", "ppsx", "pot", "potx", "odp", "otp", "odg", "vsd", "vsdx",
]);

function extensionOf(file) {
    const name = file.name || file.filename || "";
    return name.includes(".") ? name.split(".").pop().toLowerCase() : "";
}

const officePreview = {
    get isOfficeSheet() {
        return this.isOfficeFile && SHEET_EXT.has(extensionOf(this));
    },
    get isOffice() {
        return this.isOfficeFile && !this.uploading;
    },
    get isOfficeFile() {
        if (this.type === "url" || !this.id || this.isPdf || this.isImage || this.isText || this.isVideo) {
            return false;
        }
        const ext = extensionOf(this);
        return SHEET_EXT.has(ext) || DOC_EXT.has(ext);
    },
    get isViewable() {
        return super.isViewable || this.isOffice;
    },
    get defaultSource() {
        return this.isOffice ? `/rapidlink_preview/view/${this.id}` : super.defaultSource;
    },
};

patch(FileModel.prototype, officePreview);
patch(Attachment.prototype, officePreview);
