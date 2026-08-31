> ## Documentation Index
> Fetch the complete documentation index at: https://docs.corti.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Upload Recording

> Upload a recording for a given interaction. There is a maximum limit of 120 minutes in audio duration and 150 MB in file size.



## OpenAPI

````yaml /api-reference/auto-generated-openapi.yml post /interactions/{id}/recordings/
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
  /interactions/{id}/recordings/:
    post:
      tags:
        - Recordings
      summary: Upload Recording
      description: >-
        Upload a recording for a given interaction. There is a maximum limit of
        120 minutes in audio duration and 150 MB in file size.
      operationId: recordings_upload
      parameters:
        - $ref: '#/components/parameters/Tenant-Name'
        - $ref: '#/components/parameters/CommonInteractionId'
      requestBody:
        content:
          application/octet-stream:
            schema:
              type: string
              format: binary
              description: Recording
              title: Recording
        required: true
      responses:
        '201':
          description: Returns the recording ID in the response.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/RecordingsCreateResponse'
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
          source: >
            using Corti;

            using System.IO;


            var client = new CortiClient(
                "TENANT_NAME",
                CortiClientEnvironment.Eu,
                new CortiClientAuth.ClientCredentials("client_id", "client_secret")
            );

            var file = File.OpenRead("YOUR_FILE_PATH");

            await
            client.Recordings.UploadAsync("f47ac10b-58cc-4372-a567-0e02b2c3d479",
            file);
          x-fern-sdk-language-id: c#-.net-sdk
        - lang: javascript
          label: JavaScript SDK (Server)
          source: >-
            import { CortiEnvironment, CortiClient } from "@corti/sdk";

            import { createReadStream } from "fs";


            const client = new CortiClient({
              environment: CortiEnvironment.Eu,
              auth: {
                clientId: "YOUR_CLIENT_ID",
                clientSecret: "YOUR_CLIENT_SECRET"
              },
              tenantName: "YOUR_TENANT_NAME"
            });


            const file = createReadStream("YOUR_FILE_PATH", {
              autoClose: true
            });


            const res = await client.recordings.upload(file,
            "f47ac10b-58cc-4372-a567-0e02b2c3d479");
          x-fern-sdk-language-id: javascript-sdk-(server)
        - lang: javascript
          label: JavaScript SDK (Browser)
          source: >-
            import { CortiEnvironment, CortiClient } from "@corti/sdk";


            const client = new CortiClient({
              environment: CortiEnvironment.Eu,
              auth: {
                accessToken: "YOUR_ACCESS_TOKEN"
              },
              tenantName: "YOUR_TENANT_NAME"
            });


            const file = e.target.files[0]; // where e = 'change' event on
            <input type="file">

            const res = await client.recordings.upload(file,
            "f47ac10b-58cc-4372-a567-0e02b2c3d479");
          x-fern-sdk-language-id: javascript-sdk-(browser)
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
  schemas:
    RecordingsCreateResponse:
      type: object
      required:
        - recordingId
      properties:
        recordingId:
          $ref: '#/components/schemas/UUID'
          type: string
          format: uuid
          description: The unique identifier for the created recording.
          items: {}
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