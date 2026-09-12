# Twilio

## Overview

The [Twilio](https://www.twilio.com/) Extension allows you to send messages within Twilio. It requires you to setup the Twilio authentication in the **Integrations** section of your Organization.

See Twilio's [SMS send-messages reference](https://www.twilio.com/docs/sms/send-messages) for more detail.

## Setup

To start leveraging the Twilio extension, first subscribe to the `ext-twilio` add-on that can be accessed from the LimaCharlie **Marketplace**.

![twilio](../../../assets/images/twilio.png)

After you have subscribed to the extension, setup the Twilio authentication in the `Secrets Manager` section of your organization.

Authentication in Twilio uses two components--a SID and a token. The LimaCharlie Twilio secret will combine both components in a single field like `SID/TOKEN`.

### Detection & Response

Example Response portion of a  rule that sends a message out via Twilio as the response action:

```yaml
- action: extension request
  extension action: run
  extension name: ext-twilio
  extension request:
    body: '{{ .event }}'
    from: '{{ "+10123456789" }}'
    to: '{{ "+10123456789" }}'
```

*Note that the* `{{ .event }}` *in the example above is the actual text that would be sent to the number you specify.*
