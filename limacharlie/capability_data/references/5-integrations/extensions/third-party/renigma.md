# REnigma

## About REnigma

[REnigma](https://dtrsec.com/) is an advanced malware analysis platform leveraging its unique Record and Replay technology to deliver unparalleled precision and depth. By recording every state change in a virtual machine during live execution, REnigma enables analysts to replay and analyze malware behaviors offline, down to the instruction level. This approach eliminates the risk of evasion and ensures a comprehensive capture of malicious activity. For SOC teams triaging alerts or incident responders conducting deep dives, REnigma offers rapid detonation, precision analysis, and effortless artifact extraction. Its API integrations further enhance workflows, enabling seamless automation and streamlined investigation processes.

## About the Extension

The LimaCharlie Extension for REnigma seamlessly integrates with the REnigma API, enabling automated analysis of suspicious URLs or files collected using the LimaCharlie BinLib or Artifact Extensions. When a file or URL triggers an alert in LimaCharlie, preconfigured Detection & Response () rules can automatically queue the item for further investigation in REnigma.

Through the integration, these D&R rules send the artifact or URL directly to REnigma, where it is recorded and analyzed in a controlled virtual machine environment. Analysts can then access detailed execution data, artifacts, and network patterns captured by REnigma's Record and Replay technology. This workflow not only streamlines the triage process but also provides deep insights into potential threats without requiring manual intervention at every step.

## Configuration

To use the REnigma extension, you will need your REnigma URL and API key. [Contact the REnigma team for access](https://dtrsec.com/contact.html).

![Configuration To use the REnigma extension, you will need your REnigma URL and API key](../../../assets/images/image(284).png)

## Using the Extension

You can submit a file or URL to the REnigma extension for processing in one of 2 ways:

1. Via the LimaCharlie web UI:

   1. Submit the ID of the artifact you wish to process with REnigma, and it will get uploaded and processed via a series of D&R rules. You will see the output in the `ext-renigma` sensor timeline.![You can submit a file or URL to the REnigma extension for processing in one of 2 ways: 1](../../../assets/images/image(297).png)
   2. Submit the URL you wish to analyze with REnigma, and it will get sent and processed via a series of D&R rules. You will see the output in the `ext-renigma` sensor timeline.![You can submit a file or URL to the REnigma extension for processing in one of 2 ways: 1](../../../assets/images/image(296).png)
2. Via D&R rules:

   1. Detect:

      ```yaml
      event: ingest
      op: exists
      path: /
      target: artifact_event
      artifact type: ext-binlib-bin
      ```

   2. Respond

      ```yaml
      - action: "extension request"
        extension name: "ext-renigma"
        extension action: "upload_file"
        extension request:
            file_id: '{{ .routing.log_id }}'
            disable_internet: false
      ```

LimaCharlie Extensions allow users to expand and customize their security environments by integrating third-party tools, automating workflows, and adding new capabilities. Organizations subscribe to Extensions, which are granted specific permissions to interact with their infrastructure. Extensions can be private or public, enabling tailored use or broader community sharing. This framework supports scalability, flexibility, and secure, repeatable deployments.

## Related Articles

- [BinLib](../limacharlie/binlib.md)
- [Artifacts](../limacharlie/artifact.md)
- [Using Extensions](../using-extensions.md)
- [Secure Annex](secureannex.md)
