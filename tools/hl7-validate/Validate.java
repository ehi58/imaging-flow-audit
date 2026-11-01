import ca.uhn.hl7v2.DefaultHapiContext;
import ca.uhn.hl7v2.HL7Exception;
import ca.uhn.hl7v2.HapiContext;
import ca.uhn.hl7v2.model.Message;
import ca.uhn.hl7v2.parser.PipeParser;
import ca.uhn.hl7v2.validation.impl.ValidationContextFactory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * Validate HL7 v2 ER7 files with HAPI HL7v2 (ca.uhn.hapi 2.6.0).
 *
 * HAPI picks the message structure from MSH-9 and MSH-12 and the matching
 * structures jar on the classpath (v2.8, v2.8.1 and v2.5.1 here). Parsing in
 * the default (non-lenient) mode checks the segment order and cardinality of the
 * structure; the default validation context then checks data types, such as a
 * malformed DTM, a too-long ID, or a value outside a table.
 *
 * Usage: java -cp "<jars>;out" Validate <file.hl7>... | @list.txt (one path per line)
 * Prints one line per file: "OK <file> <structure>" or "FAIL <file> <reason>";
 * exits 1 when any file fails, so a caller can use it as a positive control
 * (a deliberately broken message must make it exit 1).
 */
public class Validate {
    public static void main(String[] args) throws IOException {
        if (args.length == 0) {
            System.err.println("usage: Validate <file.hl7>...");
            System.exit(2);
        }
        HapiContext context = new DefaultHapiContext();
        context.setValidationContext(ValidationContextFactory.defaultValidation());
        PipeParser parser = context.getPipeParser();
        int failures = 0;
        java.util.List<String> files = new java.util.ArrayList<>();
        for (String arg : args) {
            if (arg.startsWith("@")) {
                // A list file, one path per line: thousands of files exceed the
                // Windows command-line limit when passed as arguments.
                for (String line : Files.readAllLines(Paths.get(arg.substring(1)), StandardCharsets.UTF_8)) {
                    if (!line.isBlank()) files.add(line.trim());
                }
            } else {
                files.add(arg);
            }
        }
        for (String arg : files) {
            Path path = Paths.get(arg);
            String text = new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
            // Files may arrive with \n endings on some systems; HAPI needs \r.
            text = text.replace("\r\n", "\r").replace("\n", "\r");
            try {
                Message message = parser.parse(text);
                String structure = message.getName();
                String version = message.getVersion();
                System.out.println("OK " + path + " " + structure + " v" + version);
            } catch (HL7Exception e) {
                failures++;
                System.out.println("FAIL " + path + " " + e.getMessage().replace('\n', ' '));
            }
        }
        System.exit(failures == 0 ? 0 : 1);
    }
}
