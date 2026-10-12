import { DiagnosticSeverity, type Diagnostic } from 'vscode-languageserver';
import type { TextDocument } from 'vscode-languageserver-textdocument';
import { analyze, type AnalyzeOptions, type Finding } from '../analyze.js';
import { RULES } from '../rules.js';

export const DIAGNOSTIC_SOURCE = 'routeros-lsp';

const SEVERITY = {
  error: DiagnosticSeverity.Error,
  warning: DiagnosticSeverity.Warning,
  information: DiagnosticSeverity.Information,
  hint: DiagnosticSeverity.Hint,
} as const;

/** Says how well founded a finding is, so a router quirk is never mistaken for the language specification. */
function describe(finding: Finding): string {
  switch (RULES[finding.rule].source) {
    case 'device':
      return `${finding.message} (RouterOS behaviour that the documentation does not describe)`;
    case 'open':
      return `${finding.message} (the documentation does not specify this)`;
    default:
      return finding.message;
  }
}

export function toDiagnostics(document: TextDocument, options: AnalyzeOptions): Diagnostic[] {
  const { findings } = analyze(document.getText(), options);
  return findings.map((finding) => ({
    range: { start: document.positionAt(finding.start), end: document.positionAt(finding.end) },
    severity: SEVERITY[finding.severity],
    code: finding.rule,
    source: DIAGNOSTIC_SOURCE,
    message: describe(finding),
  }));
}
