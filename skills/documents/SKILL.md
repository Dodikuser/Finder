---
name: documents
description: "Giving the user a downloadable file (PDF, DOCX, Markdown, CSV) with create_document, or an image from the web with send_image: when to use them and how to structure the content."
version: 1.0.0
author: Finder
license: MIT
metadata:
  hermes:
    tags: [documents, pdf, docx, report, images]
    related_skills: [source-citation, data-visualization]
---

# Documents and images

You have no file system. `create_document` and `send_image` are the way to give the user a file:
you pass content, the server builds the file and attaches it to the chat.

## create_document(title, content_markdown, format)

Use it when the user asks for a report, a file, "a PDF", "a Word document", something to send to
a supervisor or to print. Do not create files nobody asked for.

| format | for |
|---|---|
| `pdf` | a finished report to read or forward (default) |
| `docx` | a text the user will keep editing in Word |
| `md` | notes for a wiki or a repository |
| `csv` | a table for Excel — pass exactly one markdown table |

Write the whole document as markdown:
- The `title` argument becomes the document heading — do not repeat it as `# heading`.
- Structure with `##` sections: summary first, then findings, then **Sources** with links.
- Tables for comparisons (keep them to 5–6 columns so they fit an A4 page).
- Plain markdown only: no images, no raw HTML, no emoji-as-icons.
- Write it for someone who has not seen the chat: full sentences, dates, units, what was and was
  not verified.
- Same language as the conversation.

The same honesty rules as in chat apply: only facts from sources you opened, every claim with its
link, unknowns stated as unknown.

After the tool confirms, tell the user in one or two sentences what the file contains. Do not
paste the document into the chat again.

## send_image(url, caption)

Shows one image from the web in the chat: a figure from an open-access paper, a product
screenshot, a logo, a map. Requirements:
- a **direct** link to a PNG / JPEG / GIF / WebP file (find it with `page_links` or in the page text);
- `caption` says what it is and where it comes from;
- only when the picture adds something the text cannot — not for decoration.

You cannot draw or generate pictures. For charts of your own data use `create_dashboard`.
