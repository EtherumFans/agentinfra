> ## Documentation Index
> Fetch the complete documentation index at: https://docs.corti.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Predict Codes

> Predict medical codes from provided context.<br/><Note>This is a stateless endpoint, designed to predict ICD-10-CM, ICD-10-PCS, ICD-10 (international), ICD-10-UK, CIM-10-FR, ICD-10-GM, OPCS-4, OPS, CCAM and CPT codes based on input text string or documentId.<br/><br/>More than one code system may be defined in a single request.<br/><br/>Code prediction requests have two possible values for context:<br/>- `text`: One set of code prediction results will be returned based on all input text defined.<br/>- `documentId`: Code prediction will be based on that defined document only.<br/><br/>The response includes two sets of results:<br/>- `Codes`: Codes predicted by the model.<br/>- `Candidates`: Lower-confidence codes the model considered potentially relevant but excluded from the predicted set.<br/><br/>All predicted code results are based on input context defined in the request only (not other external data or assets associated with an interaction).</Note>



## OpenAPI

````yaml /api-reference/auto-generated-openapi.yml post /tools/coding/
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
  /tools/coding/:
    post:
      tags:
        - Codes
      summary: Predict Codes
      description: >-
        Predict medical codes from provided context.<br/><Note>This is a
        stateless endpoint, designed to predict ICD-10-CM, ICD-10-PCS, ICD-10
        (international), ICD-10-UK, CIM-10-FR, ICD-10-GM, OPCS-4, OPS, CCAM and
        CPT codes based on input text string or documentId.<br/><br/>More than
        one code system may be defined in a single request.<br/><br/>Code
        prediction requests have two possible values for context:<br/>- `text`:
        One set of code prediction results will be returned based on all input
        text defined.<br/>- `documentId`: Code prediction will be based on that
        defined document only.<br/><br/>The response includes two sets of
        results:<br/>- `Codes`: Codes predicted by the model.<br/>-
        `Candidates`: Lower-confidence codes the model considered potentially
        relevant but excluded from the predicted set.<br/><br/>All predicted
        code results are based on input context defined in the request only (not
        other external data or assets associated with an interaction).</Note>
      operationId: codes_predict
      parameters:
        - $ref: '#/components/parameters/Tenant-Name'
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CodesGeneralPredictRequest'
            examples:
              basic:
                summary: Predict ICD-10-CM and CPT from text
                value:
                  system:
                    - icd10cm-outpatient
                    - cpt
                  context:
                    - type: text
                      text: Short arm splint applied in ED for pain control.
              with_filter:
                summary: Predict with code filter
                value:
                  system:
                    - icd10cm-outpatient
                  context:
                    - type: text
                      text: Patient presents with uncontrolled type 2 diabetes.
                  filter:
                    include:
                      - E11
                    exclude: []
        required: true
      responses:
        '200':
          description: >-
            List of predicted codes and candidate codes per system defined in
            the request, including evidence supporting the code prediction.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/CodesGeneralResponse'
              examples:
                success:
                  summary: Example response with preselected codes and candidates
                  value:
                    codes:
                      - system: icd10cm-outpatient
                        code: R10.30
                        display: Lower abdominal pain, unspecified
                        evidences:
                          - contextIndex: 0
                            text: Example text mentioning lower abdominal pain
                            start: 0
                            end: 44
                        alternatives:
                          - code: R10.10
                            display: Upper abdominal pain, unspecified
                          - code: R10.32
                            display: Left lower quadrant pain
                    candidates:
                      - system: icd10cm-outpatient
                        code: R50.9
                        display: Fever, unspecified
                        evidences:
                          - contextIndex: 1
                            text: Example text mentioning fever
                            start: 0
                            end: 29
                        alternatives:
                          - code: R50.2
                            display: Drug induced fever
                          - code: R50.82
                            display: Postprocedural fever
                    usageInfo:
                      creditsConsumed: 123
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
        '502':
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
            await client.Codes.PredictAsync(
                new CodesGeneralPredictRequest
                {
                    System = new List<CommonCodingSystemEnum>()
                    {
                        CommonCodingSystemEnum.Icd10CmOutpatient,
                        CommonCodingSystemEnum.Cpt,
                    },
                    Context = new List<CommonAiContext>()
                    {
                        new CommonTextContext { Text = "Short arm splint applied in ED for pain control." },
                    },
                }
            );
        - lang: csharp
          label: C# .NET SDK
          source: |
            using Corti;

            var client = new CortiClient(
                "TENANT_NAME",
                CortiClientEnvironment.Eu,
                new CortiClientAuth.ClientCredentials("client_id", "client_secret")
            );
            await client.Codes.PredictAsync(
                new CodesGeneralPredictRequest
                {
                    System = new List<CommonCodingSystemEnum>() { CommonCodingSystemEnum.Icd10CmOutpatient },
                    Context = new List<CommonAiContext>()
                    {
                        new CommonTextContext { Text = "Patient presents with uncontrolled type 2 diabetes." },
                    },
                    Filter = new CodesFilter
                    {
                        Include = new List<string>() { "E11" },
                        Exclude = new List<string>() { "exclude" },
                    },
                }
            );
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
            await client.codes.predict({
                system: ["icd10cm-outpatient", "cpt"],
                context: [{
                        type: "text",
                        text: "Short arm splint applied in ED for pain control."
                    }]
            });
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
            await client.codes.predict({
                system: ["icd10cm-outpatient"],
                context: [{
                        type: "text",
                        text: "Patient presents with uncontrolled type 2 diabetes."
                    }],
                filter: {
                    include: ["E11"],
                    exclude: ["exclude"]
                }
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
  schemas:
    CodesGeneralPredictRequest:
      type: object
      required:
        - system
        - context
      properties:
        system:
          type: array
          description: List of coding systems for prediction
          uniqueItems: true
          minItems: 1
          maxItems: 15
          items:
            $ref: '#/components/schemas/CommonCodingSystemEnum'
          example:
            - icd10cm-outpatient
            - cpt
        context:
          type: array
          description: >-
            Select either `text` or `documentId` as input context to the model
            for code prediction. Evidence indices in the response map to this
            array.
          items:
            $ref: '#/components/schemas/CommonAIContext'
        filter:
          $ref: '#/components/schemas/CodesFilter'
          description: Optional filter to restrict predicted codes.
    CodesGeneralResponse:
      type: object
      required:
        - codes
        - candidates
        - usageInfo
      properties:
        codes:
          type: array
          description: Codes predicted by the model.
          items:
            $ref: '#/components/schemas/CodesGeneralReadResponse'
        candidates:
          type: array
          description: >-
            Lower-confidence codes the model considered potentially relevant but
            excluded from the predicted set.
          items:
            $ref: '#/components/schemas/CodesGeneralReadResponse'
        usageInfo:
          $ref: '#/components/schemas/CommonUsageInfo'
          type: object
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
    CommonCodingSystemEnum:
      type: string
      enum:
        - icd10cm-inpatient
        - icd10cm-outpatient
        - icd10pcs
        - cpt
        - icd10int-inpatient
        - icd10int-outpatient
        - icd10uk-inpatient
        - icd10uk-outpatient
        - cim10fr-inpatient
        - cim10fr-outpatient
        - icd10gm-inpatient
        - icd10gm-outpatient
        - opcs4
        - ops
        - ccam
    CommonAIContext:
      oneOf:
        - $ref: '#/components/schemas/CommonTextContext'
        - $ref: '#/components/schemas/CommonDocumentIDContext'
    CodesFilter:
      type: object
      description: Optional filter to restrict the set of codes the model can predict.
      properties:
        include:
          type: array
          description: >-
            Codes or categories to include. When empty, the full set of codes
            for the requested systems is used.
          items:
            type: string
          example:
            - E11
        exclude:
          type: array
          description: Codes or categories to subtract from the include set.
          items:
            type: string
        expand:
          type: boolean
          description: >-
            When true (default), category codes are expanded to their leaf
            codes.
    CodesGeneralReadResponse:
      type: object
      description: Predicted or candidate code record.
      required:
        - system
        - code
        - display
      properties:
        system:
          $ref: '#/components/schemas/CommonCodingSystemEnum'
          description: The coding system used
        code:
          type: string
          description: The medical code
          example: T93.3
        display:
          type: string
          description: Description of the medical code
        evidences:
          type: array
          description: The evidence for the prediction
          items:
            type: object
            required:
              - contextIndex
              - text
              - start
              - end
            properties:
              contextIndex:
                type: integer
                description: Index from the context input array
              text:
                type: string
                description: Part of input text
              start:
                type: integer
                description: >-
                  0-based start character offset of the evidence span
                  (inclusive)
              end:
                type: integer
                description: 0-based end character offset of the evidence span (exclusive)
        alternatives:
          type: array
          description: Codes the model also considered for this prediction.
          items:
            type: object
            description: The alternative code
            required:
              - code
              - display
            properties:
              code:
                type: string
                description: The medical code
              display:
                type: string
                description: Description of the medical code
    CommonUsageInfo:
      type: object
      description: Credits consumed for this request.
      required:
        - creditsConsumed
      properties:
        creditsConsumed:
          type: number
    CommonTextContext:
      type: object
      title: Text
      required:
        - type
        - text
      properties:
        type:
          type: string
          enum:
            - text
          description: |
            The type of context, always "text" in this context.
        text:
          type: string
          description: |
            A text string to be used as input to the model.
          minLength: 1
    CommonDocumentIDContext:
      type: object
      title: DocumentID
      required:
        - type
        - documentId
      properties:
        type:
          type: string
          enum:
            - documentId
          description: |
            The type of context, always "documentId" in this context.
        documentId:
          type: string
          description: A referenced document ID to be used as input to the model.
  securitySchemes:
    AuthorizationHeader:
      type: http
      description: Input your token
      scheme: bearer

````