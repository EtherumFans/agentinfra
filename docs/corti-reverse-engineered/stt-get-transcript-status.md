> ## Documentation Index
> Fetch the complete documentation index at: https://docs.corti.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Get Transcript Status

> Poll for transcript creation status.<br/><Note>Status of `completed` indicates the transcript is finalized.<br/>If the transcript is retrieved while status is `processing`, then it will be incomplete.<br/>Status of `failed` indicate the transcript was not created successfully; please retry.</Note>



## OpenAPI

````yaml /api-reference/auto-generated-openapi.yml get /interactions/{id}/transcripts/{transcriptId}/status
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
  /interactions/{id}/transcripts/{transcriptId}/status:
    get:
      tags:
        - Transcripts
      summary: Get Transcript Status
      description: >-
        Poll for transcript creation status.<br/><Note>Status of `completed`
        indicates the transcript is finalized.<br/>If the transcript is
        retrieved while status is `processing`, then it will be
        incomplete.<br/>Status of `failed` indicate the transcript was not
        created successfully; please retry.</Note>
      operationId: transcripts_get_status
      parameters:
        - $ref: '#/components/parameters/Tenant-Name'
        - $ref: '#/components/parameters/CommonInteractionId'
        - $ref: '#/components/parameters/CommonTranscriptId'
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TranscriptsStatusResponse'
        '404':
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
            await client.Transcripts.GetStatusAsync(
                "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "f47ac10b-58cc-4372-a567-0e02b2c3d479"
            );
        - lang: javascript
          label: JavaScript SDK
          source: >
            import { CortiClient, CortiEnvironment } from "@corti/sdk";


            const client = new CortiClient({
                environment: CortiEnvironment.Eu,
                auth: {
                    clientId: "YOUR_CLIENT_ID",
                    clientSecret: "YOUR_CLIENT_SECRET"
                },
                tenantName: "YOUR_TENANT_NAME"
            });

            await
            client.transcripts.getStatus("f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "f47ac10b-58cc-4372-a567-0e02b2c3d479");
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
    CommonTranscriptId:
      name: transcriptId
      in: path
      description: The unique identifier of the transcript. Must be a valid UUID.
      required: true
      schema:
        $ref: '#/components/schemas/UUID'
  schemas:
    TranscriptsStatusResponse:
      type: object
      required:
        - status
      properties:
        status:
          $ref: '#/components/schemas/TranscriptsStatusEnum'
          description: The current status of the transcript processing.
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
    TranscriptsStatusEnum:
      type: string
      description: Possible values for transcript processing status.
      enum:
        - completed
        - processing
        - failed
  securitySchemes:
    AuthorizationHeader:
      type: http
      description: Input your token
      scheme: bearer

````