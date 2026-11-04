import Foundation

public struct PrinterQueue: Sendable, Identifiable, Hashable {
    public let id: String
    public let name: String
    public let isDefault: Bool
    public let statusDescription: String

    public init(id: String, name: String, isDefault: Bool = false, statusDescription: String = "") {
        self.id = id
        self.name = name
        self.isDefault = isDefault
        self.statusDescription = statusDescription
    }
}

public struct PrintJobResult: Sendable {
    public let success: Bool
    public let jobId: String?
    public let backend: String
    public let message: String
}

public final class CUPSRawSpooler: Sendable {
    public init() {}

    /// Discovers all available CUPS printer queues on the system.
    public static func discoverQueues() -> [PrinterQueue] {
        var queues: [PrinterQueue] = []
        var defaultQueueName: String? = nil

        // Get default destination
        let destProc = Process()
        destProc.executableURL = URL(fileURLWithPath: "/usr/bin/lpstat")
        destProc.arguments = ["-d"]
        let destPipe = Pipe()
        destProc.standardOutput = destPipe
        try? destProc.run()
        destProc.waitUntilExit()

        let destData = destPipe.fileHandleForReading.readDataToEndOfFile()
        if let destStr = String(data: destData, encoding: .utf8) {
            // "system default destination: Canon_G600_series"
            if let match = destStr.components(separatedBy: "system default destination: ").last?.trimmingCharacters(in: .whitespacesAndNewlines) {
                defaultQueueName = match
            }
        }

        // Get printer statuses
        let statProc = Process()
        statProc.executableURL = URL(fileURLWithPath: "/usr/bin/lpstat")
        statProc.arguments = ["-p"]
        let statPipe = Pipe()
        statProc.standardOutput = statPipe
        try? statProc.run()
        statProc.waitUntilExit()

        let statData = statPipe.fileHandleForReading.readDataToEndOfFile()
        if let statStr = String(data: statData, encoding: .utf8) {
            // Lines like: "printer Canon_G600_series is idle.  enabled since ..."
            for line in statStr.components(separatedBy: "\n") where line.hasPrefix("printer ") {
                let parts = line.dropFirst("printer ".count).components(separatedBy: " ")
                guard let qName = parts.first, !qName.isEmpty else { continue }
                let isDef = (qName == defaultQueueName)
                queues.append(PrinterQueue(
                    id: qName,
                    name: qName,
                    isDefault: isDef,
                    statusDescription: line
                ))
            }
        }

        // Fallback if no specific lpstat -p line was parsed
        if queues.isEmpty, let defName = defaultQueueName, !defName.isEmpty {
            queues.append(PrinterQueue(id: defName, name: defName, isDefault: true, statusDescription: "Default system printer"))
        }

        return queues
    }

    /// Submits a raw URF raster buffer directly to the CUPS spooler using -o raw.
    public static func printRaw(
        urfData: Data,
        queueName: String,
        jobName: String,
        paper: PaperSpec,
        borderless: Bool = true
    ) throws -> PrintJobResult {
        let tmpDir = FileManager.default.temporaryDirectory
        let tmpFile = tmpDir.appendingPathComponent("g640rip_\(UUID().uuidString).urf")

        try urfData.write(to: tmpFile)
        defer {
            try? FileManager.default.removeItem(at: tmpFile)
        }

        var mediaName = paper.name
        if paper.name == "4x6" {
            mediaName = borderless ? "4x6.Fullbleed" : "4x6"
        } else if paper.name == "A4" {
            mediaName = borderless ? "A4.Fullbleed" : "A4"
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/lp")
        process.arguments = [
            "-d", queueName,
            "-o", "raw",
            "-t", jobName,
            "-o", "media=\(mediaName)",
            "-o", "PageSize=\(mediaName)",
            tmpFile.path
        ]

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe

        try process.run()
        process.waitUntilExit()

        let outData = pipe.fileHandleForReading.readDataToEndOfFile()
        let output = String(data: outData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""

        if process.terminationStatus == 0 {
            // Output usually: "request id is Canon_G600_series-60 (1 file(s))"
            var jobId: String? = nil
            if let match = output.components(separatedBy: "request id is ").last?.components(separatedBy: " ").first {
                jobId = match
            }
            return PrintJobResult(
                success: true,
                jobId: jobId,
                backend: "CUPS-Raw (\(queueName))",
                message: output
            )
        } else {
            throw G640Error.cupsSpoolerError("lp failed with code \(process.terminationStatus): \(output)")
        }
    }

    /// Cancels a specific job or all jobs for a queue.
    public static func cancelJobs(queueName: String, jobId: String? = nil) {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/bin/cancel")
        if let jId = jobId, !jId.isEmpty {
            proc.arguments = [jId]
        } else {
            proc.arguments = ["-a", queueName]
        }
        try? proc.run()
        proc.waitUntilExit()
    }

    /// Returns list of active jobs in the queue.
    public static func getQueueStatus(queueName: String) -> String {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/bin/lpstat")
        proc.arguments = ["-o", queueName]
        let pipe = Pipe()
        proc.standardOutput = pipe
        try? proc.run()
        proc.waitUntilExit()

        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        return String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }
}
