declare module "newrelic" {
  interface BrowserTimingHeaderOptions {
    hasToRemoveScriptWrapper?: boolean;
    allowTransactionlessInjection?: boolean;
  }

  interface NewRelicAgent {
    collector: {
      isConnected?: () => boolean;
    };
    on: (event: string, listener: () => void) => void;
    once: (event: string, listener: () => void) => void;
    removeListener: (event: string, listener: () => void) => void;
  }

  interface NewRelic {
    agent: NewRelicAgent;
    getBrowserTimingHeader?: (options?: BrowserTimingHeaderOptions) => string;
  }

  const newrelic: NewRelic;
  export default newrelic;
}
