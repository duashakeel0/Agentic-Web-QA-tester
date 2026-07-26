export type LiveRunMessage =
  | { type: "status"; message: string }
  | { type: "done"; url: string; title: string; message: string }
  | { type: "error"; message: string };
