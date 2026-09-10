# Security

## What this application does with your documents

LayoutKeep runs on your machine. A document goes to a network service **only** when you point it
at one:

- **A local model** (LM Studio, Ollama, llama.cpp): the text goes to that server, which is yours.
- **DeepL or any cloud endpoint you configure**: the text of each segment is sent to that
  service. The document itself is not uploaded; the text is.
- **No provider configured**: nothing leaves the machine.

API keys are stored in the operating system's credential store through `keyring`, never in a
configuration file. The project's own settings hold the endpoint address and model name only.

Crash reports (`%APPDATA%\LayoutKeep\layoutkeep_crash.log`) contain a Python traceback and no
document text.

## Reporting a vulnerability

Please open a [security advisory](https://github.com/Legendnoobe/LayoutKeep/security/advisories/new)
rather than a public issue. A report that includes a document which triggers the problem is the
most useful; if it is private, say so and describe its structure instead.

There is no bounty, and no promise of a fixed timeline - this is a small project. What is
promised is that the report will be read, that you will hear back either way, and that a fix
will say what it fixes.

## What is already accounted for

- **XML external entities.** Every parser in the project is constructed with
  `resolve_entities=False`, so a document cannot make the reader fetch a file or a URL.
- **Archive traversal.** EPUB and DOCX are read entry by entry from the zip and never extracted
  to disk, so a crafted path inside an archive cannot write outside a directory.
- **Credentials.** See above: keyring only.

## Supported versions

The latest release. This is a one-person project; older versions receive nothing.
