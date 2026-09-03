namespace Icoder.Sdk;

/// <summary>A2A v0.3 Context plus v1 synchronous/asynchronous Task operations.</summary>
public sealed class A2AResource(ICoDerClient client)
{
    private static readonly IReadOnlyDictionary<string, string> ProtocolHeaders =
        new Dictionary<string, string> { ["A2A-Protocol-Version"] = "0.3" };
    private static readonly IReadOnlyDictionary<string, string> V1ProtocolHeaders =
        new Dictionary<string, string> { ["A2A-Version"] = "1.0" };
    private static readonly HashSet<string> V1SettledStates =
    [
        "TASK_STATE_COMPLETED",
        "TASK_STATE_FAILED",
        "TASK_STATE_CANCELED",
        "TASK_STATE_REJECTED",
        "TASK_STATE_INPUT_REQUIRED",
        "TASK_STATE_AUTH_REQUIRED",
    ];

    public Task<A2AMessage> MessageSendTextAsync(
        string agentId,
        string text,
        string? contextId = null,
        string? messageId = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(text, nameof(text));
        return MessageSendAsync(
            agentId,
            new A2AMessageRequest
            {
                Parts = [new A2APart { Kind = "text", Text = text }],
                ContextId = contextId,
                MessageId = messageId ?? $"msg-{Guid.NewGuid()}",
            },
            cancellationToken,
            requestOptions);
    }

    public Task<A2AMessage> MessageSendAsync(
        string agentId,
        A2AMessageRequest message,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(agentId, nameof(agentId));
        Guard.NotNull(message, nameof(message));
        return client.SendA2AAsync<A2AMessage>(
            HttpMethod.Post,
            $"/api/icoder/agents/{Uri.EscapeDataString(agentId)}/v1/message:send",
            new
            {
                jsonrpc = "2.0",
                id = $"rpc-{Guid.NewGuid()}",
                method = "message/send",
                @params = new { message },
            },
            ProtocolHeaders,
            cancellationToken,
            requestOptions);
    }

    public IAsyncEnumerable<A2AStreamEvent> MessageStreamTextAsync(
        string agentId,
        string text,
        string? contextId = null,
        string? messageId = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(agentId, nameof(agentId));
        Guard.NotNullOrWhiteSpace(text, nameof(text));
        var message = new A2AMessageRequest
        {
            Parts = [new A2APart { Kind = "text", Text = text }],
            ContextId = contextId,
            MessageId = messageId ?? $"msg-{Guid.NewGuid()}",
        };
        return client.SendA2AStreamAsync(
            $"/api/icoder/agents/{Uri.EscapeDataString(agentId)}/v1/message:stream",
            new
            {
                jsonrpc = "2.0",
                id = $"rpc-{Guid.NewGuid()}",
                method = "message/stream",
                @params = new { message },
            },
            ProtocolHeaders,
            cancellationToken,
            requestOptions);
    }

    public Task<A2AContextResponse> GetContextAsync(
        string agentId,
        string contextId,
        int limit = 100,
        int offset = 0,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(agentId, nameof(agentId));
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        if (limit is < 1 or > 500) throw new ArgumentOutOfRangeException(nameof(limit));
        if (offset < 0) throw new ArgumentOutOfRangeException(nameof(offset));
        return client.SendAsync<A2AContextResponse>(
            HttpMethod.Get,
            $"/api/icoder/agents/{Uri.EscapeDataString(agentId)}/v1/contexts/" +
            $"{Uri.EscapeDataString(contextId)}?limit={limit}&offset={offset}",
            headers: ProtocolHeaders,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<A2AContextDeleted> DeleteContextAsync(
        string contextId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        return client.SendA2AAsync<A2AContextDeleted>(
            HttpMethod.Delete,
            $"/api/icoder/contexts/{Uri.EscapeDataString(contextId)}",
            headers: ProtocolHeaders,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<A2AV1SendResponse> MessageSendV1TextAsync(
        string agentId,
        string text,
        bool returnImmediately = false,
        string? contextId = null,
        string? messageId = null,
        string? taskId = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(text, nameof(text));
        return MessageSendV1Async(
            agentId,
            new A2AV1MessageRequest
            {
                Parts =
                [
                    new A2AV1Part
                    {
                        Text = text,
                        MediaType = "text/plain",
                    },
                ],
                ContextId = contextId,
                TaskId = taskId,
                MessageId = messageId ?? $"msg-{Guid.NewGuid()}",
            },
            returnImmediately,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<A2AV1SendResponse> MessageSendV1Async(
        string agentId,
        A2AV1MessageRequest message,
        bool returnImmediately = false,
        IReadOnlyList<string>? acceptedOutputModes = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(agentId, nameof(agentId));
        Guard.NotNull(message, nameof(message));
        if (message.Parts.Count == 0)
        {
            throw new ArgumentException("At least one A2A v1 Part is required.", nameof(message));
        }
        return client.SendA2AV1Async<A2AV1SendResponse>(
            HttpMethod.Post,
            $"/api/v2/agentic/agents/{Uri.EscapeDataString(agentId)}/message:send",
            new
            {
                message,
                configuration = new
                {
                    returnImmediately,
                    acceptedOutputModes,
                },
            },
            V1ProtocolHeaders,
            cancellationToken,
            requestOptions);
    }

    public IAsyncEnumerable<A2AStreamEvent> MessageStreamV1TextAsync(
        string agentId,
        string text,
        bool returnImmediately = false,
        string? contextId = null,
        string? messageId = null,
        string? taskId = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(text, nameof(text));
        return MessageStreamV1Async(
            agentId,
            new A2AV1MessageRequest
            {
                Parts =
                [
                    new A2AV1Part
                    {
                        Text = text,
                        MediaType = "text/plain",
                    },
                ],
                ContextId = contextId,
                TaskId = taskId,
                MessageId = messageId ?? $"msg-{Guid.NewGuid()}",
            },
            returnImmediately,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public IAsyncEnumerable<A2AStreamEvent> MessageStreamV1Async(
        string agentId,
        A2AV1MessageRequest message,
        bool returnImmediately = false,
        IReadOnlyList<string>? acceptedOutputModes = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(agentId, nameof(agentId));
        Guard.NotNull(message, nameof(message));
        if (message.Parts.Count == 0)
        {
            throw new ArgumentException(
                "At least one A2A v1 Part is required.", nameof(message));
        }
        return client.SendA2AStreamAsync(
            $"/api/v2/agentic/agents/{Uri.EscapeDataString(agentId)}/message:stream",
            new
            {
                message,
                configuration = new
                {
                    returnImmediately,
                    acceptedOutputModes,
                },
            },
            V1ProtocolHeaders,
            cancellationToken,
            requestOptions);
    }

    public Task<A2AV1Task> GetTaskV1Async(
        string agentId,
        string taskId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(agentId, nameof(agentId));
        Guard.NotNullOrWhiteSpace(taskId, nameof(taskId));
        return client.SendA2AV1Async<A2AV1Task>(
            HttpMethod.Get,
            $"/api/v2/agentic/agents/{Uri.EscapeDataString(agentId)}/tasks/" +
            Uri.EscapeDataString(taskId),
            headers: V1ProtocolHeaders,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<A2AV1TaskList> ListTasksV1Async(
        string agentId,
        string? contextId = null,
        string? status = null,
        int pageSize = 50,
        string? pageToken = null,
        string? statusTimestampAfter = null,
        bool includeArtifacts = false,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(agentId, nameof(agentId));
        if (pageSize is < 1 or > 100) throw new ArgumentOutOfRangeException(nameof(pageSize));
        var query = new List<string>
        {
            $"pageSize={pageSize}",
            $"includeArtifacts={includeArtifacts.ToString().ToLowerInvariant()}",
        };
        if (!string.IsNullOrWhiteSpace(contextId))
            query.Add($"contextId={Uri.EscapeDataString(contextId)}");
        if (!string.IsNullOrWhiteSpace(status))
            query.Add($"status={Uri.EscapeDataString(status)}");
        if (!string.IsNullOrWhiteSpace(pageToken))
            query.Add($"pageToken={Uri.EscapeDataString(pageToken)}");
        if (!string.IsNullOrWhiteSpace(statusTimestampAfter))
            query.Add($"statusTimestampAfter={Uri.EscapeDataString(statusTimestampAfter)}");
        return client.SendA2AV1Async<A2AV1TaskList>(
            HttpMethod.Get,
            $"/api/v2/agentic/agents/{Uri.EscapeDataString(agentId)}/tasks?" +
            string.Join("&", query),
            headers: V1ProtocolHeaders,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<A2AV1Task> CancelTaskV1Async(
        string agentId,
        string taskId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(agentId, nameof(agentId));
        Guard.NotNullOrWhiteSpace(taskId, nameof(taskId));
        return client.SendA2AV1Async<A2AV1Task>(
            HttpMethod.Post,
            $"/api/v2/agentic/agents/{Uri.EscapeDataString(agentId)}/tasks/" +
            $"{Uri.EscapeDataString(taskId)}:cancel",
            new { },
            V1ProtocolHeaders,
            cancellationToken,
            requestOptions);
    }

    public async Task<A2AV1Task> WaitTaskV1Async(
        string agentId,
        string taskId,
        TimeSpan? timeout = null,
        TimeSpan? pollInterval = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        var effectiveTimeout = timeout ?? TimeSpan.FromSeconds(60);
        var effectiveInterval = pollInterval ?? TimeSpan.FromMilliseconds(250);
        if (effectiveTimeout <= TimeSpan.Zero) throw new ArgumentOutOfRangeException(nameof(timeout));
        if (effectiveInterval <= TimeSpan.Zero) throw new ArgumentOutOfRangeException(nameof(pollInterval));
        var deadline = DateTimeOffset.UtcNow + effectiveTimeout;
        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var task = await GetTaskV1Async(
                    agentId, taskId, cancellationToken, requestOptions)
                .ConfigureAwait(false);
            if (V1SettledStates.Contains(task.Status.State)) return task;
            var remaining = deadline - DateTimeOffset.UtcNow;
            if (remaining <= TimeSpan.Zero)
            {
                throw new TimeoutException(
                    $"A2A v1 Task '{taskId}' did not reach a settled state.");
            }
            await Task.Delay(
                remaining < effectiveInterval ? remaining : effectiveInterval,
                cancellationToken).ConfigureAwait(false);
        }
    }

    public IAsyncEnumerable<A2AStreamEvent> SubscribeTaskV1Async(
        string agentId,
        string taskId,
        int afterSequence = 0,
        string? lastEventId = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(agentId, nameof(agentId));
        Guard.NotNullOrWhiteSpace(taskId, nameof(taskId));
        if (afterSequence < 0) throw new ArgumentOutOfRangeException(nameof(afterSequence));
        return client.SendA2AV1TaskEventsAsync(
            $"/api/v2/agentic/agents/{Uri.EscapeDataString(agentId)}/tasks/" +
            $"{Uri.EscapeDataString(taskId)}:subscribe?afterSequence={afterSequence}",
            V1ProtocolHeaders,
            lastEventId,
            cancellationToken,
            requestOptions);
    }

    public Task<AgenticTracePage> ExportContextTracesAsync(
        string contextId,
        int pageSize = 50,
        string? pageToken = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        if (pageSize is < 1 or > 200) throw new ArgumentOutOfRangeException(nameof(pageSize));
        var path = $"/api/v2/agentic/contexts/{Uri.EscapeDataString(contextId)}/trace?pageSize={pageSize}";
        if (!string.IsNullOrWhiteSpace(pageToken))
            path += $"&pageToken={Uri.EscapeDataString(pageToken)}";
        return client.SendAsync<AgenticTracePage>(
            HttpMethod.Get, path, headers: V1ProtocolHeaders,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<AgenticContextPage> ListContextsV2Async(
        string? agentId = null,
        DateTimeOffset? from = null,
        DateTimeOffset? to = null,
        int pageSize = 50,
        string? pageToken = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        if (pageSize is < 1 or > 200) throw new ArgumentOutOfRangeException(nameof(pageSize));
        var query = new List<string> { $"pageSize={pageSize}" };
        if (!string.IsNullOrWhiteSpace(agentId))
            query.Add($"agentId={Uri.EscapeDataString(agentId)}");
        if (from is not null)
            query.Add($"from={Uri.EscapeDataString(from.Value.ToUniversalTime().ToString("O"))}");
        if (to is not null)
            query.Add($"to={Uri.EscapeDataString(to.Value.ToUniversalTime().ToString("O"))}");
        if (!string.IsNullOrWhiteSpace(pageToken))
            query.Add($"pageToken={Uri.EscapeDataString(pageToken)}");
        return client.SendA2AV1Async<AgenticContextPage>(
            HttpMethod.Get,
            "/api/v2/agentic/contexts?" + string.Join("&", query),
            headers: V1ProtocolHeaders,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<AgenticContextResource> GetContextV2Async(
        string contextId,
        int? historyLength = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        if (historyLength is < 0 or > 100)
            throw new ArgumentOutOfRangeException(nameof(historyLength));
        var path = $"/api/v2/agentic/contexts/{Uri.EscapeDataString(contextId)}";
        if (historyLength is not null) path += $"?historyLength={historyLength}";
        return client.SendA2AV1Async<AgenticContextResource>(
            HttpMethod.Get, path, headers: V1ProtocolHeaders,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task DeleteContextV2Async(
        string contextId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        return client.SendNoContentAsync(
            HttpMethod.Delete,
            $"/api/v2/agentic/contexts/{Uri.EscapeDataString(contextId)}",
            cancellationToken,
            V1ProtocolHeaders,
            requestOptions);
    }

    public Task<AgenticContextTaskPage> ListContextTasksV2Async(
        string contextId,
        int pageSize = 50,
        string? pageToken = null,
        int historyLength = 0,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        if (pageSize is < 1 or > 200) throw new ArgumentOutOfRangeException(nameof(pageSize));
        if (historyLength is < 0 or > 100)
            throw new ArgumentOutOfRangeException(nameof(historyLength));
        var query = new List<string>
        {
            $"pageSize={pageSize}", $"historyLength={historyLength}",
        };
        if (!string.IsNullOrWhiteSpace(pageToken))
            query.Add($"pageToken={Uri.EscapeDataString(pageToken)}");
        return client.SendA2AV1Async<AgenticContextTaskPage>(
            HttpMethod.Get,
            $"/api/v2/agentic/contexts/{Uri.EscapeDataString(contextId)}/tasks?" +
            string.Join("&", query),
            headers: V1ProtocolHeaders,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<A2AV1Task> GetContextTaskV2Async(
        string contextId,
        string taskId,
        int? historyLength = null,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        Guard.NotNullOrWhiteSpace(taskId, nameof(taskId));
        if (historyLength is < 0 or > 100)
            throw new ArgumentOutOfRangeException(nameof(historyLength));
        var path = $"/api/v2/agentic/contexts/{Uri.EscapeDataString(contextId)}/tasks/" +
            Uri.EscapeDataString(taskId);
        if (historyLength is not null) path += $"?historyLength={historyLength}";
        return client.SendA2AV1Async<A2AV1Task>(
            HttpMethod.Get, path, headers: V1ProtocolHeaders,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<AgenticArtifact> GetTaskArtifactV2Async(
        string contextId,
        string taskId,
        string artifactId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        Guard.NotNullOrWhiteSpace(taskId, nameof(taskId));
        Guard.NotNullOrWhiteSpace(artifactId, nameof(artifactId));
        return client.SendA2AV1Async<AgenticArtifact>(
            HttpMethod.Get,
            $"/api/v2/agentic/contexts/{Uri.EscapeDataString(contextId)}/tasks/" +
            $"{Uri.EscapeDataString(taskId)}/artifacts/{Uri.EscapeDataString(artifactId)}",
            headers: V1ProtocolHeaders,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<AgenticArtifactObject> UploadTaskArtifactObjectV2Async(
        string contextId,
        string taskId,
        string artifactId,
        byte[] content,
        string filename,
        string mediaType,
        string dataClassification = "deidentified",
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        Guard.NotNullOrWhiteSpace(taskId, nameof(taskId));
        Guard.NotNullOrWhiteSpace(artifactId, nameof(artifactId));
        Guard.NotNull(content, nameof(content));
        Guard.NotNullOrWhiteSpace(filename, nameof(filename));
        if (content.Length is < 1 or > 5 * 1024 * 1024)
            throw new ArgumentOutOfRangeException(nameof(content));
        if (mediaType is not ("text/plain" or "application/json" or "application/pdf"))
            throw new ArgumentOutOfRangeException(nameof(mediaType));
        if (dataClassification is not ("deidentified" or "clinical-sensitive"))
            throw new ArgumentOutOfRangeException(nameof(dataClassification));
        return client.SendA2AV1Async<AgenticArtifactObject>(
            HttpMethod.Post,
            ArtifactObjectRoot(contextId, taskId, artifactId),
            new
            {
                raw = Convert.ToBase64String(content),
                filename,
                mediaType,
                dataClassification,
            },
            V1ProtocolHeaders,
            cancellationToken,
            requestOptions);
    }

    public Task<AgenticArtifactObjectPage> ListTaskArtifactObjectsV2Async(
        string contextId,
        string taskId,
        string artifactId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        Guard.NotNullOrWhiteSpace(taskId, nameof(taskId));
        Guard.NotNullOrWhiteSpace(artifactId, nameof(artifactId));
        return client.SendA2AV1Async<AgenticArtifactObjectPage>(
            HttpMethod.Get,
            ArtifactObjectRoot(contextId, taskId, artifactId),
            headers: V1ProtocolHeaders,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<AgenticArtifactDownloadAuthorization>
        AuthorizeTaskArtifactObjectDownloadV2Async(
            string contextId,
            string taskId,
            string artifactId,
            string objectId,
            string purposeOfUse,
            int expiresInSeconds = 60,
            CancellationToken cancellationToken = default,
            ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(objectId, nameof(objectId));
        if (purposeOfUse is not ("treatment" or "payment" or "healthcare_operations"))
            throw new ArgumentOutOfRangeException(nameof(purposeOfUse));
        if (expiresInSeconds is < 1 or > 300)
            throw new ArgumentOutOfRangeException(nameof(expiresInSeconds));
        return client.SendA2AV1Async<AgenticArtifactDownloadAuthorization>(
            HttpMethod.Post,
            $"{ArtifactObjectRoot(contextId, taskId, artifactId)}/" +
            $"{Uri.EscapeDataString(objectId)}:authorize-download",
            new { purposeOfUse, expiresInSeconds },
            V1ProtocolHeaders,
            cancellationToken,
            requestOptions);
    }

    /// <summary>Consume once with this client's Bearer identity; never retry.</summary>
    public Task<byte[]> DownloadAuthorizedArtifactObjectV2Async(
        AgenticArtifactDownloadAuthorization authorization,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNull(authorization, nameof(authorization));
        Guard.NotNullOrWhiteSpace(authorization.Part.Url, nameof(authorization.Part.Url));
        return client.SendBytesAsync(
            HttpMethod.Get, authorization.Part.Url, cancellationToken,
            requestOptions, allowRetries: false);
    }

    public Task DeleteTaskArtifactObjectV2Async(
        string contextId,
        string taskId,
        string artifactId,
        string objectId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(objectId, nameof(objectId));
        return client.SendNoContentAsync(
            HttpMethod.Delete,
            $"{ArtifactObjectRoot(contextId, taskId, artifactId)}/" +
            Uri.EscapeDataString(objectId),
            cancellationToken,
            V1ProtocolHeaders,
            requestOptions);
    }

    private static string ArtifactObjectRoot(
        string contextId, string taskId, string artifactId)
    {
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        Guard.NotNullOrWhiteSpace(taskId, nameof(taskId));
        Guard.NotNullOrWhiteSpace(artifactId, nameof(artifactId));
        return $"/api/v2/agentic/contexts/{Uri.EscapeDataString(contextId)}/tasks/" +
            $"{Uri.EscapeDataString(taskId)}/artifacts/" +
            $"{Uri.EscapeDataString(artifactId)}/objects";
    }

    public Task<AgenticAgentUsage> GetAgentUsageAsync(
        string agentId,
        DateTimeOffset? from = null,
        DateTimeOffset? to = null,
        string granularity = "day",
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(agentId, nameof(agentId));
        if (granularity != "minute" && granularity != "hour" &&
            granularity != "day" && granularity != "week")
            throw new ArgumentOutOfRangeException(nameof(granularity));
        var query = new List<string> {
            $"granularity={Uri.EscapeDataString(granularity)}"
        };
        if (from is not null)
            query.Add($"from={Uri.EscapeDataString(from.Value.ToUniversalTime().ToString("O"))}");
        if (to is not null)
            query.Add($"to={Uri.EscapeDataString(to.Value.ToUniversalTime().ToString("O"))}");
        var path = $"/api/v2/agentic/agents/{Uri.EscapeDataString(agentId)}/usage?" +
            string.Join("&", query);
        return client.SendAsync<AgenticAgentUsage>(
            HttpMethod.Get, path, headers: V1ProtocolHeaders,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<A2AV1AgentCard> GetAgentCardAsync(
        string agentId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(agentId, nameof(agentId));
        return client.SendAsync<A2AV1AgentCard>(
            HttpMethod.Get,
            $"/api/v2/agentic/agents/{Uri.EscapeDataString(agentId)}/" +
            ".well-known/agent-card.json",
            headers: V1ProtocolHeaders,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task<AgenticFeedback> SubmitTaskFeedbackAsync(
        string contextId,
        string taskId,
        AgenticFeedbackInput feedback,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        Guard.NotNullOrWhiteSpace(taskId, nameof(taskId));
        Guard.NotNull(feedback, nameof(feedback));
        return client.SendAsync<AgenticFeedback>(
            HttpMethod.Post,
            FeedbackPath(contextId, taskId),
            feedback,
            V1ProtocolHeaders,
            cancellationToken,
            requestOptions);
    }

    public Task<AgenticFeedbackList> ListTaskFeedbackAsync(
        string contextId,
        string taskId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        Guard.NotNullOrWhiteSpace(taskId, nameof(taskId));
        return client.SendAsync<AgenticFeedbackList>(
            HttpMethod.Get,
            FeedbackPath(contextId, taskId),
            headers: V1ProtocolHeaders,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task DeleteTaskFeedbackAsync(
        string contextId,
        string taskId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        Guard.NotNullOrWhiteSpace(taskId, nameof(taskId));
        return client.SendNoContentAsync(
            HttpMethod.Delete, FeedbackPath(contextId, taskId), cancellationToken,
            V1ProtocolHeaders, requestOptions);
    }

    public Task<FeedbackTrainingAuthorization> AuthorizeFeedbackForTrainingAsync(
        string contextId,
        string taskId,
        string feedbackId,
        FeedbackTrainingAuthorizationInput authorization,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        Guard.NotNullOrWhiteSpace(taskId, nameof(taskId));
        Guard.NotNullOrWhiteSpace(feedbackId, nameof(feedbackId));
        Guard.NotNull(authorization, nameof(authorization));
        return client.SendAsync<FeedbackTrainingAuthorization>(
            HttpMethod.Put,
            FeedbackTrainingAuthorizationPath(contextId, taskId, feedbackId),
            authorization,
            V1ProtocolHeaders,
            cancellationToken,
            requestOptions);
    }

    public Task<FeedbackTrainingAuthorization> GetFeedbackTrainingAuthorizationAsync(
        string contextId,
        string taskId,
        string feedbackId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        Guard.NotNullOrWhiteSpace(taskId, nameof(taskId));
        Guard.NotNullOrWhiteSpace(feedbackId, nameof(feedbackId));
        return client.SendAsync<FeedbackTrainingAuthorization>(
            HttpMethod.Get,
            FeedbackTrainingAuthorizationPath(contextId, taskId, feedbackId),
            headers: V1ProtocolHeaders,
            cancellationToken: cancellationToken, requestOptions: requestOptions);
    }

    public Task RevokeFeedbackTrainingAuthorizationAsync(
        string contextId,
        string taskId,
        string feedbackId,
        CancellationToken cancellationToken = default,
        ICoDerRequestOptions? requestOptions = null)
    {
        Guard.NotNullOrWhiteSpace(contextId, nameof(contextId));
        Guard.NotNullOrWhiteSpace(taskId, nameof(taskId));
        Guard.NotNullOrWhiteSpace(feedbackId, nameof(feedbackId));
        return client.SendNoContentAsync(
            HttpMethod.Delete,
            FeedbackTrainingAuthorizationPath(contextId, taskId, feedbackId),
            cancellationToken,
            V1ProtocolHeaders,
            requestOptions);
    }

    private static string FeedbackPath(string contextId, string taskId) =>
        $"/api/v2/agentic/contexts/{Uri.EscapeDataString(contextId)}/tasks/" +
        $"{Uri.EscapeDataString(taskId)}/feedback";

    private static string FeedbackTrainingAuthorizationPath(
        string contextId, string taskId, string feedbackId) =>
        FeedbackPath(contextId, taskId) + "/" +
        Uri.EscapeDataString(feedbackId) + "/training-authorization";
}
