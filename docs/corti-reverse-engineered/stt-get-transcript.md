> ## Documentation Index
> Fetch the complete documentation index at: https://docs.corti.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Get Transcript

> Retrieve a transcript from a specific interaction.<br/><Note>Each interaction may have more than one transcript associated with it. Use the List Transcript request (`GET /interactions/{id}/transcripts/`) to see all transcriptIds available for the interaction.<br/><br/>The client can poll this Get Transcript endpoint (`GET /interactions/{id}/transcripts/{transcriptId}/status`) for transcript status changes:<br/>- `200 OK` with status `processing`, `completed`, or `failed`<br/>- `404 Not Found` if the `interactionId` or `transcriptId` are invalid<br/><br/>Status of `completed` indicates the transcript is finalized. If the transcript is retrieved while status is `processing`, then it will be incomplete.</Note>



## OpenAPI

````yaml /api-reference/auto-generated-openapi.yml get /interactions/{id}/transcripts/{transcriptId}
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
  /interactions/{id}/transcripts/{transcriptId}:
    get:
      tags:
        - Transcripts
      summary: Get Transcript
      description: >-
        Retrieve a transcript from a specific interaction.<br/><Note>Each
        interaction may have more than one transcript associated with it. Use
        the List Transcript request (`GET /interactions/{id}/transcripts/`) to
        see all transcriptIds available for the interaction.<br/><br/>The client
        can poll this Get Transcript endpoint (`GET
        /interactions/{id}/transcripts/{transcriptId}/status`) for transcript
        status changes:<br/>- `200 OK` with status `processing`, `completed`, or
        `failed`<br/>- `404 Not Found` if the `interactionId` or `transcriptId`
        are invalid<br/><br/>Status of `completed` indicates the transcript is
        finalized. If the transcript is retrieved while status is `processing`,
        then it will be incomplete.</Note>
      operationId: transcripts_get
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
                $ref: '#/components/schemas/TranscriptsResponse'
        '400':
          description: RFC9457
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '401':
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
          source: |
            using Corti;

            var client = new CortiClient(
                "TENANT_NAME",
                CortiClientEnvironment.Eu,
                new CortiClientAuth.ClientCredentials("client_id", "client_secret")
            );
            await client.Transcripts.GetAsync(
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

            await client.transcripts.get("f47ac10b-58cc-4372-a567-0e02b2c3d479",
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
    TranscriptsResponse:
      type: object
      required:
        - id
        - metadata
        - transcripts
        - usageInfo
        - recordingId
        - status
      properties:
        id:
          $ref: '#/components/schemas/UUID'
          type: string
          format: uuid
          description: The unique identifier of the transcript.
          items: {}
        metadata:
          $ref: '#/components/schemas/TranscriptsMetadata'
          type: object
          description: >-
            Additional information about the participants involved in the
            transcript.
        transcripts:
          type: array
          description: An array of transcripts.
          nullable: true
          items:
            $ref: '#/components/schemas/CommonTranscriptResponse'
        usageInfo:
          $ref: '#/components/schemas/CommonUsageInfo'
          type: object
        recordingId:
          $ref: '#/components/schemas/UUID'
          type: string
          format: uuid
          description: The unique identifier for the associated recording.
          items: {}
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
    TranscriptsMetadata:
      type: object
      properties:
        participantsRoles:
          type: array
          items:
            $ref: '#/components/schemas/TranscriptsParticipant'
          nullable: true
    CommonTranscriptResponse:
      type: object
      required:
        - channel
        - participant
        - speakerId
        - text
        - start
        - end
      properties:
        channel:
          type: integer
          description: The channel associated with this phrase/utterance.
        participant:
          type: integer
          description: The identifier of the participant.
        speakerId:
          type: integer
          description: Id to tag an identified speaker. Auto-increments.
        text:
          type: string
          description: The spoken phrase or utterance extracted from the audio.
        start:
          type: integer
          description: Start time in milliseconds for phrase/utterance.
        end:
          type: integer
          description: End time in milliseconds for phrase/utterance.
    CommonUsageInfo:
      type: object
      description: Credits consumed for this request.
      required:
        - creditsConsumed
      properties:
        creditsConsumed:
          type: number
    TranscriptsStatusEnum:
      type: string
      description: Possible values for transcript processing status.
      enum:
        - completed
        - processing
        - failed
    TranscriptsParticipant:
      type: object
      required:
        - channel
        - role
      properties:
        channel:
          type: integer
          description: The audio channel to associate with a participant role.
        role:
          $ref: '#/components/schemas/TranscriptsParticipantRoleEnum'
          description: >-
            The role of the participant (e.g., 'doctor', 'patient', use
            'multiple' for single channel).
    TranscriptsParticipantRoleEnum:
      type: string
      enum:
        - doctor
        - patient
        - multiple
  securitySchemes:
    AuthorizationHeader:
      type: http
      description: Input your token
      scheme: bearer

````