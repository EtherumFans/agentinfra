using System.Net.Http;
using System.Net.WebSockets;
using System.Runtime.InteropServices;
using System.Security.Cryptography;

namespace Icoder.Sdk;

internal static class Compatibility
{
    private static readonly object RandomLock = new();
    private static readonly Random RandomSource = new();

    public static readonly HttpMethod Patch = new("PATCH");

    public static double NextDouble()
    {
        lock (RandomLock)
        {
            return RandomSource.NextDouble();
        }
    }

    public static double Clamp(double value, double minimum, double maximum)
        => value < minimum ? minimum : value > maximum ? maximum : value;

    public static bool IsAsciiLetterOrDigit(char value)
        => value is >= 'a' and <= 'z' or >= 'A' and <= 'Z' or >= '0' and <= '9';

    public static ArraySegment<byte> AsArraySegment(ReadOnlyMemory<byte> value)
        => MemoryMarshal.TryGetArray(value, out ArraySegment<byte> segment)
            ? segment
            : new ArraySegment<byte>(value.ToArray());

    public static void ZeroMemory(byte[] value)
    {
#if NETSTANDARD2_0
        Array.Clear(value, 0, value.Length);
#else
        CryptographicOperations.ZeroMemory(value);
#endif
    }

    public static async Task<Stream> ReadAsStreamAsync(
        HttpContent content,
        CancellationToken cancellationToken)
    {
#if NETSTANDARD2_0
        cancellationToken.ThrowIfCancellationRequested();
        using var registration = cancellationToken.Register(content.Dispose);
        try
        {
            var stream = await content.ReadAsStreamAsync().ConfigureAwait(false);
            cancellationToken.ThrowIfCancellationRequested();
            return stream;
        }
        catch (ObjectDisposedException) when (cancellationToken.IsCancellationRequested)
        {
            throw new OperationCanceledException(cancellationToken);
        }
#else
        return await content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
#endif
    }

    public static async Task<byte[]> ReadAsByteArrayAsync(
        HttpContent content,
        CancellationToken cancellationToken)
    {
#if NETSTANDARD2_0
        cancellationToken.ThrowIfCancellationRequested();
        using var registration = cancellationToken.Register(content.Dispose);
        try
        {
            var bytes = await content.ReadAsByteArrayAsync().ConfigureAwait(false);
            cancellationToken.ThrowIfCancellationRequested();
            return bytes;
        }
        catch (ObjectDisposedException) when (cancellationToken.IsCancellationRequested)
        {
            throw new OperationCanceledException(cancellationToken);
        }
#else
        return await content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false);
#endif
    }

    public static async Task<string?> ReadLineAsync(
        StreamReader reader,
        CancellationToken cancellationToken)
    {
#if NETSTANDARD2_0
        cancellationToken.ThrowIfCancellationRequested();
        using var registration = cancellationToken.Register(reader.Dispose);
        try
        {
            return await reader.ReadLineAsync().ConfigureAwait(false);
        }
        catch (ObjectDisposedException) when (cancellationToken.IsCancellationRequested)
        {
            throw new OperationCanceledException(cancellationToken);
        }
#else
        return await reader.ReadLineAsync(cancellationToken).ConfigureAwait(false);
#endif
    }
}
