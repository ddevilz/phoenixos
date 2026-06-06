export function extractComponents(text: string): string[] {
  // file-path-like tokens; extended with C/C++ extensions for the demo's lib/transfer.c
  const re = /[\w./-]+\.(?:py|ts|js|go|java|rb|rs|c|cpp|h)/g;
  return [...new Set(text.match(re) ?? [])];
}
