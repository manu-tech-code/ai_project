package com.alm.parser.controller;

import com.alm.parser.dto.ParseRequest;
import com.alm.parser.dto.ParseResponse;
import com.alm.parser.service.JavaParserWalker;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.nio.file.Files;
import java.nio.file.Path;

/**
 * REST endpoint that triggers a full UCG parse of a local Java repository.
 *
 * <pre>
 * POST /parse
 * Content-Type: application/json
 *
 * { "repoPath": "/absolute/path/to/java/source/root" }
 * </pre>
 */
@RestController
@RequestMapping("/parse")
public class ParseController {

    private static final Logger log = LoggerFactory.getLogger(ParseController.class);

    private final JavaParserWalker walker;

    public ParseController(JavaParserWalker walker) {
        this.walker = walker;
    }

    /**
     * Parse the Java source tree rooted at {@code request.repoPath()}.
     *
     * @param request JSON body containing the {@code repoPath} field
     * @return a {@link ParseResponse} with nodes, edges, and any per-file error messages
     */
    @PostMapping(consumes = "application/json", produces = "application/json")
    public ResponseEntity<ParseResponse> parse(@RequestBody ParseRequest request) {

        String repoPath = request.repoPath();

        if (repoPath == null || repoPath.isBlank()) {
            throw new IllegalArgumentException("repoPath must not be blank");
        }

        Path root = Path.of(repoPath);
        if (!Files.exists(root)) {
            throw new IllegalArgumentException("repoPath does not exist: " + repoPath);
        }
        if (!Files.isDirectory(root)) {
            throw new IllegalArgumentException("repoPath must be a directory: " + repoPath);
        }

        log.info("Received parse request for: {}", repoPath);

        try {
            ParseResponse response = walker.walkRepository(repoPath);
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            // Wrap unexpected IO / runtime failures — GlobalExceptionHandler will produce the JSON body
            throw new RuntimeException("Failed to walk repository at " + repoPath + ": " + e.getMessage(), e);
        }
    }
}
