package com.alm.parser;

import com.alm.parser.dto.ParseResponse;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Integration tests for the {@code /parse} endpoint.
 *
 * <p>A temporary directory containing a minimal Java source file is created for
 * each test so the service always has real files to parse without relying on
 * any external repository being present on the test runner.
 */
@SpringBootTest
@AutoConfigureMockMvc
class ParseControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @TempDir
    Path tempDir;

    private static final String SAMPLE_CLASS = """
            package com.example;

            import java.util.List;

            /**
             * A minimal sample class used only by the parser integration test.
             */
            public class SampleService {

                private String name;

                public String getName() {
                    return name;
                }

                public void setName(String name) {
                    this.name = name;
                }

                public List<String> process(List<String> input) {
                    return input.stream()
                            .map(String::toUpperCase)
                            .toList();
                }
            }
            """;

    @BeforeEach
    void writeSampleFile() throws Exception {
        // Mimic a typical Maven layout so JavaParserTypeSolver can find the package root
        Path pkgDir = tempDir.resolve("com/example");
        Files.createDirectories(pkgDir);
        Files.writeString(pkgDir.resolve("SampleService.java"), SAMPLE_CLASS);
    }

    // ---------------------------------------------------------------------- happy path

    @Test
    void parseReturns200AndContainsExpectedNodes() throws Exception {
        String body = objectMapper.writeValueAsString(Map.of("repoPath", tempDir.toString()));

        MvcResult result = mockMvc.perform(post("/parse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nodes").isArray())
                .andExpect(jsonPath("$.edges").isArray())
                .andExpect(jsonPath("$.errors").isArray())
                .andReturn();

        ParseResponse response = objectMapper.readValue(
                result.getResponse().getContentAsString(), ParseResponse.class);

        List<Map<String, Object>> nodes = response.nodes();
        assertThat(nodes).isNotEmpty();

        // There must be at least one module node for our file
        boolean hasModuleNode = nodes.stream()
                .anyMatch(n -> "module".equals(n.get("type")));
        assertThat(hasModuleNode).as("Expected a module node").isTrue();

        // There must be at least one class node for SampleService
        boolean hasClassNode = nodes.stream()
                .anyMatch(n -> "class".equals(n.get("type"))
                        && "SampleService".equals(n.get("name")));
        assertThat(hasClassNode).as("Expected a class node for SampleService").isTrue();

        // There must be function nodes for at least the three declared methods
        long functionCount = nodes.stream()
                .filter(n -> "function".equals(n.get("type")))
                .count();
        assertThat(functionCount).as("Expected at least 3 function nodes").isGreaterThanOrEqualTo(3);
    }

    @Test
    void parseReturns200WithEdgesContainRelationships() throws Exception {
        String body = objectMapper.writeValueAsString(Map.of("repoPath", tempDir.toString()));

        MvcResult result = mockMvc.perform(post("/parse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andReturn();

        ParseResponse response = objectMapper.readValue(
                result.getResponse().getContentAsString(), ParseResponse.class);

        boolean hasContainsEdge = response.edges().stream()
                .anyMatch(e -> "contains".equals(e.get("type")));
        assertThat(hasContainsEdge).as("Expected at least one 'contains' edge").isTrue();
    }

    // ---------------------------------------------------------------------- error cases

    @Test
    void parseReturnsBadRequestWhenRepoPathIsBlank() throws Exception {
        String body = objectMapper.writeValueAsString(Map.of("repoPath", ""));

        mockMvc.perform(post("/parse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void parseReturnsBadRequestWhenRepoPathDoesNotExist() throws Exception {
        String body = objectMapper.writeValueAsString(
                Map.of("repoPath", "/this/path/definitely/does/not/exist/ever"));

        mockMvc.perform(post("/parse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void parseHandlesMalformedJavaFileGracefully() throws Exception {
        // Write a broken Java file alongside the valid one
        Path pkgDir = tempDir.resolve("com/example");
        Files.writeString(pkgDir.resolve("Broken.java"), "this is not valid java {{{ !!!");

        String body = objectMapper.writeValueAsString(Map.of("repoPath", tempDir.toString()));

        MvcResult result = mockMvc.perform(post("/parse")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())   // service must still return 200
                .andReturn();

        ParseResponse response = objectMapper.readValue(
                result.getResponse().getContentAsString(), ParseResponse.class);

        // The valid SampleService file should still have been parsed
        boolean hasClassNode = response.nodes().stream()
                .anyMatch(n -> "SampleService".equals(n.get("name")));
        assertThat(hasClassNode).as("SampleService should still be present despite a broken peer file").isTrue();

        // The broken file error should be recorded (not silently swallowed)
        assertThat(response.errors())
                .as("Expected an error entry for the malformed file")
                .isNotEmpty();
    }

    // ---------------------------------------------------------------------- actuator

    @Test
    void actuatorHealthEndpointIsAvailable() throws Exception {
        mockMvc.perform(post("/actuator/health")
                        .contentType(MediaType.APPLICATION_JSON))
                // Actuator health is GET, not POST — but a 405 confirms the endpoint exists
                .andExpect(result ->
                        assertThat(result.getResponse().getStatus())
                                .isNotEqualTo(404));
    }
}
