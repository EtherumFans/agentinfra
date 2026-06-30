> ## Documentation Index
> Fetch the complete documentation index at: https://docs.corti.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Get Recording

> Retrieve a specific recording for a given interaction.



## OpenAPI

````yaml /api-reference/auto-generated-openapi.yml get /interactions/{id}/recordings/{recordingId}
openapi: 3.0.0
info:
  title: Corti API
  version: 2.0.0
servers:
  - url: https://api.{environment}.corti.app/v2/
    variables:
      environment:
        default: eu
        enum:
          - us
          - eu
security:
  - AuthorizationHeader:
      - bearer
tags:
  - name: Interactions
  - name: Recordings
  - name: Transcripts
  - name: Facts
  - name: Codes
  - name: Languages
  - name: Guided Documents
  - name: Guided Templates
  - name: Guided Sections
  - name: Documents (Classic)
  - name: Templates (Classic)
paths:
  /interactions/{id}/recordings/{recordingId}:
    get:
      tags:
        - Recordings
      summary: Get Recording
      description: Retrieve a specific recording for a given interaction.
      operationId: recordings_get
      parameters:
        - $ref: '#/components/parameters/Tenant-Name'
        - $ref: '#/components/parameters/CommonInteractionId'
        - $ref: '#/components/parameters/CommonRecordingId'
      responses:
        '200':
          description: Binary content of the recording file.
          content:
            text/plain:
              schema:
                type: string
                format: binary
        '400':
          description: RFC9457
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '403':
          description: RFC9457
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '404':
          description: RFC9457
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '500':
          description: RFC9457
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '504':
          description: RFC9457
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
      x-codeSamples:
        - lang: csharp
          label: C# .NET SDK
          source: |
            using Corti;

            var client = new CortiClient(
                "TENANT_NAME",
                CortiClientEnvironment.Eu,
                new CortiClientAuth.ClientCredentials("client_id", "client_secret")
            );
            await client.Recordings.GetAsync("id", "recordingId");
        - lang: javascript
          label: JavaScript SDK
          source: |
            import { CortiClient, CortiEnvironment } from "@corti/sdk";

            const client = new CortiClient({
                environment: CortiEnvironment.Eu,
                auth: {
                    clientId: "YOUR_CLIENT_ID",
                    clientSecret: "YOUR_CLIENT_SECRET"
                },
                tenantName: "YOUR_TENANT_NAME"
            });
            await client.recordings.get("id", "recordingId");
        - lang: javascript
          label: JavaScript SDK (Browser)
          source: >-
            import { CortiClient, CortiEnvironment } from "@corti/sdk";


            const client = new CortiClient({
              environment: CortiEnvironment.Eu,
              auth: {
                accessToken: "YOUR_ACCESS_TOKEN"
              },
              tenantName: "YOUR_TENANT_NAME"
            });


            const fileData = await
            client.recordings.get("f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "f47ac10b-58cc-4372-a567-0e02b2c3d479");

            const blob = await fileData.blob();


            const anchor: HTMLAnchorElement = document.createElement('a');

            const url = URL.createObjectURL(blob);

            anchor.href = url;

            anchor.download = "YOUR_FILE_NAME";

            document.body.appendChild(anchor);

            anchor.click();

            document.body.removeChild(anchor);

            URL.revokeObjectURL(url);
          x-fern-sdk-language-id: javascript-sdk-(browser)
        - lang: javascript
          label: JavaScript SDK (Server)
          source: >-
            import { CortiEnvironment, CortiClient } from "@corti/sdk";

            import { createWriteStream } from "fs";

            import { Readable } from "stream";

            import { ReadableStream } from "node:stream/web";


            const client = new CortiClient({
              environment: CortiEnvironment.Eu,
              auth: {
                clientId: "YOUR_CLIENT_ID",
                clientSecret: "YOUR_CLIENT_SECRET"
              },
              tenantName: "YOUR_TENANT_NAME"
            });


            const getResponse = await
            client.recordings.get("f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "f47ac10b-58cc-4372-a567-0e02b2c3d479");

            const webStream = getResponse.stream() as
            ReadableStream<Uint8Array>;

            const nodeReadable = Readable.from(webStream);

            const writeStream = createWriteStream("YOUR_FILE_PATH");


            nodeReadable.pipe(writeStream, { end: true });
          x-fern-sdk-language-id: javascript-sdk-(server)
components:
  parameters:
    Tenant-Name:
      name: Tenant-Name
      in: header
      description: >-
        Identifies a distinct entity within Corti's multi-tenant system. Ensures
        correct routing and authentication of the request.
      required: true
      example: base
      schema:
        type: string
        description: >-
          Identifies a distinct entity within Corti's multi-tenant system.
          Ensures correct routing and authentication of the request.
        example: base
    CommonInteractionId:
      name: id
      in: path
      description: The unique identifier of the interaction. Must be a valid UUID.
      required: true
      schema:
        $ref: '#/components/schemas/UUID'
    CommonRecordingId:
      name: recordingId
      in: path
      description: The unique identifier of the recording. Must be a valid UUID.
      required: true
      schema:
        $ref: '#/components/schemas/UUID'
  schemas:
    ErrorResponse:
      type: object
      required:
        - requestid
        - status
        - type
        - detail
      properties:
        requestid:
          type: string
        status:
          type: integer
        type:
          type: string
        detail:
          type: string
        validationErrors:
          type: array
          items:
            type: object
            additionalProperties:
              type: string
    UUID:
      type: string
      items: {}
      format: uuid
      example: f47ac10b-58cc-4372-a567-0e02b2c3d479
  securitySchemes:
    AuthorizationHeader:
      type: http
      description: Input your token
      scheme: bearer

````