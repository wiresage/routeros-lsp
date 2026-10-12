import { NAME, VERSION } from './version.js';

const USAGE = `${NAME} ${VERSION}

Language server for MikroTik RouterOS scripts (.rsc).

Usage:
  ${NAME} --stdio        Run the language server over stdin/stdout
  ${NAME} --version      Print the version
  ${NAME} --help         Print this help
`;

function main(argv: string[]): number {
  if (argv.includes('--version') || argv.includes('-v')) {
    process.stdout.write(`${VERSION}\n`);
    return 0;
  }
  if (argv.includes('--help') || argv.includes('-h')) {
    process.stdout.write(USAGE);
    return 0;
  }
  process.stderr.write(`${NAME}: the language server is not implemented yet.\n`);
  return 2;
}

process.exitCode = main(process.argv.slice(2));
