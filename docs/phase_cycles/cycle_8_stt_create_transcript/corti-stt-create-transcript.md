> ## Documentation Index
> Fetch the complete documentation index at: https://docs.corti.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Create Transcript

> Create a transcript from an audio file uploaded to the interaction via `/recordings` endpoint.<br/><Note>Each interaction may have more than one audio file and transcript associated with it. Audio files up to 120 minutes in total audio duration and  150 MB in size may be used.<br/><br/>By default, requests will process synchronously for 25 seconds before timeout, upon which processing will continue asynchronously. Set the `async` parameter to true to receive the location header immediately and process the request asynchronously. Read more [here](https://docs.corti.ai/stt/transcripts).</Note>



## OpenAPI

````yaml /api-reference/auto-generated-openapi.yml post /interactions/{id}/transcripts/
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
  /interactions/{id}/transcripts/:
    post:
      tags:
        - Transcripts
      summary: Create Transcript
      description: >-
        Create a transcript from an audio file uploaded to the interaction via
        `/recordings` endpoint.<br/><Note>Each interaction may have more than
        one audio file and transcript associated with it. Audio files up to 120
        minutes in total audio duration and  150 MB in size may be
        used.<br/><br/>By default, requests will process synchronously for 25
        seconds before timeout, upon which processing will continue
        asynchronously. Set the `async` parameter to true to receive the
        location header immediately and process the request asynchronously. Read
        more [here](https://docs.corti.ai/stt/transcripts).</Note>
      operationId: transcripts_create
      parameters:
        - $ref: '#/components/parameters/Tenant-Name'
        - $ref: '#/components/parameters/CommonInteractionId'
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/TranscriptsCreateRequest'
        required: true
      responses:
        '201':
          description: >-
            Returns the generated transcript, including participant roles and
            timestamps for each utterance.
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
            await client.Transcripts.CreateAsync(
                "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                new TranscriptsCreateRequest
                {
                    RecordingId = "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                    PrimaryLanguage = "en",
                }
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
            client.transcripts.create("f47ac10b-58cc-4372-a567-0e02b2c3d479", {
                recordingId: "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                primaryLanguage: "en"
            });
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
    TranscriptsCreateRequest:
      type: object
      required:
        - recordingId
        - primaryLanguage
      properties:
        recordingId:
          $ref: '#/components/schemas/UUID'
          type: string
          format: uuid
          description: The unique identifier for the recording.
          items: {}
        primaryLanguage:
          type: string
          example: en
          description: >-
            The primary spoken language of the recording. Check
            https://docs.corti.ai/stt/languages for more.
        spokenPunctuation:
          type: boolean
          description: >-
            When true, converts spoken punctuation such as 'period' or 'slash'
            into symbols (e.g., '.', '/'). When enabled, automatic punctuation
            is turned off. Takes precedence over `automaticPunctuation` when
            both are enabled.
        automaticPunctuation:
          type: boolean
          description: >-
            When true, automatically punctuates and capitalizes the transcript.
            Defaults to true. Overridden by `spokenPunctuation` when both are
            enabled.
        isDictation:
          type: boolean
          deprecated: true
          description: >-
            **Deprecated** — replaced by `spokenPunctuation` and
            `automaticPunctuation`. Ignored when either of those fields is
            provided. When `true` and neither new field is provided, it is
            treated as `spokenPunctuation: true` (automatic punctuation off). No
            removal date is currently planned.
        isMultichannel:
          type: boolean
          description: If true, each audio channel is transcribed separately.
        diarize:
          type: boolean
          description: >-
            If true, separates speakers within an audio channel returning
            incrementing ids for transcript segments.
        participants:
          type: array
          description: >-
            An array of participants, each specifying a role and an assigned
            audio channel in the recording. Leave empty when shouldDiarize: true
          items:
            $ref: '#/components/schemas/TranscriptsParticipant'
        async:
          type: boolean
          description: >-
            If true, the request will return immediately with a 202 status and
            the transcript will be processed asynchronously. Poll [Get
            Transcript Status](/api-reference/transcripts/get-transcript-status)
            to check transcript processing status - `processing`, `completed`,
            `failed`.
        replacements:
          type: array
          description: >-
            Define replacements to have terms (single words or multi-word
            phrases) replaced in final text output with your preferred style.
            For example, replace "BID" with "twice daily". Configuration is case
            insensitive and limited to 1,000 replacements per stream.
          items:
            type: object
            properties:
              find:
                type: string
                description: The term to be replaced, such as "BID".
              replace:
                type: string
                description: The preferred replacement for the term, such as "twice daily".
            required:
              - find
              - replace
        keyterms:
          type: object
          description: >-
            Define words, terms, and phrases to be recognized by Corti
            speech-to-text. Especially useful for proper nouns (e.g., surnames),
            but also supportive of words not being recognized consistently.
            Configuration is case sensitive and limited to 1,000 key terms per
            stream.
          properties:
            terms:
              type: array
              description: Ordered list of words to be recognized.
              items:
                type: object
                properties:
                  term:
                    type: string
                    description: >-
                      The word to be recognized, defined in its expected written
                      form.
                required:
                  - term
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