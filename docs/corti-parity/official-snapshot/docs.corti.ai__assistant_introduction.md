> ## Documentation Index
> Fetch the complete documentation index at: https://docs.corti.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Introduction to Embedded Assistant API

> Access an API for embedding Corti Assistant in your workflow

The Corti Embedded Assistant API enables seamless integration of Corti Assistant into host applications, such as Electronic Health Record (EHR) systems, web-based clinical portals, or native applications using embedded WebViews. The implementation provides a robust, consistent, and secure interface for parent applications to control and interact with embedded Corti Assistant.

<Tip>
  The details outlined below are for you to embed the Corti Assistant "AI scribe solution" natively within your application. To learn more about the full Corti API, please see more [here](/api-reference/welcome)
</Tip>

***

## Quick start guides

Get started quickly with our platform-specific integration guides:

<Card title="React Web App" icon="react" href="/assistant/guides/react-integration">
  Complete guide for React applications with the Web Component API
</Card>

<Info>
  **C#/.NET Desktop Guide Coming Soon**

  A complete integration guide for WPF, WinForms, and .NET MAUI applications using WebView2 is coming in Q1 2026. In the meantime, the [Web Component API](/assistant/web-component-api) works with any WebView-based application.
</Info>

***

## Overview

The Embedded Assistant API is a communication interface that allows your application to embed and control Corti Assistant within your own application interface. It provides programmatic control over authentication, session management, interaction creation, document generation, and more.

The API enables two-way communication between your application and the embedded Corti Assistant, allowing you to:

* Authenticate users and manage sessions
* Create and manage clinical interactions
* Configure the Assistant interface and appearance
* Control recording functionality
* Receive real-time events and updates
* Access generated documents and transcripts

***

## Requirements

Before getting started, ensure you have:

* **Created an OAuth Client for Corti Assistant**: You'll need to [create a Corti Assistant specific client](mailto:help@corti.aien/articles/11400088-creating-an-api-client#h_239039d8fe) from the [Developer Console](https://console.corti.app).
* **Modern browser or WebView**: For web applications, use a modern browser (Chrome, Firefox, Safari, or Edge). For native apps, use a modern WebView (WebView2, WKWebView, or Chromium-based WebView)
* **HTTPS**: The embedded Assistant must be loaded over HTTPS (required for microphone access)
* **Microphone permissions**: Your application must request and handle microphone permissions appropriately
* **OAuth2 client**: You'll need an OAuth2 client configured for user-based authentication

## Available regions

* **EU**: [https://assistant.eu.corti.app](https://assistant.eu.corti.app)
* **EU MD**: [https://assistantmd.eu.corti.app](https://assistantmd.eu.corti.app) (medical device compliant)
* **US**: [https://assistant.us.corti.app](https://assistant.us.corti.app)

## Integration methods

The Embedded Assistant API offers three integration methods. For most use cases, we recommend the **Web Component API** for its simplicity and broad compatibility.

For detailed comparison and guidance, see the [Integration Method Comparison Guide](/assistant/integrations-overview).

### Web Component API (recommended)

Works for all scenarios: iframe, WebView, same-origin, and cross-origin. Framework-agnostic with built-in React support and full TypeScript definitions.

[**Web Component API Documentation**](/assistant/web-component-api) | [**Full Examples**](https://github.com/corticph/corti-examples/tree/main/embedded-assistant)

### Alternative methods

* [**PostMessage API**](/assistant/postmessage-api) - Lower-level iframe communication (not recommended for new integrations)
* [**Window API**](/assistant/window-api) - Same-origin direct access for specific use cases

## Documentation

* [**Web Component API**](/assistant/web-component-api) (Recommended) - Complete guide with vanilla TypeScript and React examples
* [**PostMessage API**](/assistant/postmessage-api) - Lower-level API for specific use cases
* [**Window API**](/assistant/window-api) - Same-origin direct API access
* [**Integration Method Comparison**](/assistant/integrations-overview) - Detailed comparison and selection guide
* [**API Reference**](/assistant/api-reference) - Complete reference for all methods, events, and integration patterns
* [**Embedded Reliability**](/assistant/reliability-timeouts) - Timeout and retry guidance for critical lifecycle events
* [**OAuth Authentication**](/assistant/authentication) - Guide for implementing OAuth2 authentication flows
* [**Examples Repository**](https://github.com/corticph/corti-examples) - Full working examples

## Next steps

1. Follow a [platform-specific guide](#quick-start-guides) to get started quickly
2. Review the [OAuth Authentication Guide](/assistant/authentication) to set up user authentication
3. Choose your [integration method](/assistant/integrations-overview) based on your use case
4. Add [timeout and retry handling](/assistant/reliability-timeouts) for lifecycle events such as `interaction.loaded`
5. Consult the [API Reference](/assistant/api-reference) for all available methods and events

<Note>
  Please [contact us](mailto:help@corti.ai) for help or questions.
</Note>
