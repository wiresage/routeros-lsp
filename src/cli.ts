import { createConnection, ProposedFeatures } from 'vscode-languageserver/node';
import { createServer } from './server.js';
import { NAME, VERSION } from './version.js';

const USAGE = `${NAME} ${VERSION}

Language server for MikroTik RouterOS scripts (.rsc).

Usage:
  ${NAME} --stdio        Run the language server over stdin/stdout
  ${NAME} --version      Print the version
  ${NAME} --help         Print this help
`;

function main(argv: string[]): number | undefined {
  if (argv.includes('--version') || argv.includes('-v')) {
    process.stdout.write(`${VERSION}\n`);
    return 0;
  }
  if (argv.includes('--help') || argv.includes('-h')) {
    process.stdout.write(USAGE);
    return 0;
  }
  if (!argv.includes('--stdio')) {
    process.stderr.write(`${NAME}: no transport given, use --stdio.\n\n${USAGE}`);
    return 2;
  }

  // stdout carries the protocol and nothing else; anything that logs there would corrupt it.
  console.log = console.error;
  console.info = console.error;
  const connection = createConnection(ProposedFeatures.all, process.stdin, process.stdout);
  createServer(connection);
  connection.listen();
  return undefined;
}

const code = main(process.argv.slice(2));
if (code !== undefined) process.exitCode = code;
