declare module 'pagedjs' {
  interface FlowResult {
    total: number;
    performance: number;
    size: { width: { value: number; unit: string }; height: { value: number; unit: string } };
    pages: unknown[];
  }

  export class Previewer {
    constructor(options?: Record<string, unknown>);
    preview(
      content: DocumentFragment | Node,
      stylesheets: Array<string | Record<string, string>>,
      renderTo: HTMLElement,
    ): Promise<FlowResult>;
  }

  export class Chunker {
    constructor(content?: Node, renderTo?: HTMLElement, options?: Record<string, unknown>);
    flow(content: Node, renderTo: HTMLElement): Promise<FlowResult>;
    pages: unknown[];
    total: number;
  }

  export class Polisher {
    constructor(setup?: boolean);
    setup(): void;
    add(...stylesheets: Array<string | Record<string, string>>): Promise<void>;
  }
}
