# ZAP Scanning Report

ZAP by [Checkmarx](https://checkmarx.com/).


## Summary of Alerts

| Risk Level | Number of Alerts |
| --- | --- |
| High | 0 |
| Medium | 0 |
| Low | 0 |
| Informational | 1 |




## Insights

| Level | Reason | Site | Description | Statistic |
| --- | --- | --- | --- | --- |
| Low | Warning |  | ZAP errors logged - see the zap.log file for details | 1    |
| Low | Warning |  | ZAP warnings logged - see the zap.log file for details | 80    |
| Info | Informational |  | Percentage of network failures | 39 % |
| Info | Informational | http://localhost:8080 | Percentage of responses with status code 2xx | 97 % |
| Info | Informational | http://localhost:8080 | Percentage of responses with status code 4xx | 2 % |
| Info | Informational | http://localhost:8080 | Percentage of endpoints with content type application/javascript | 19 % |
| Info | Informational | http://localhost:8080 | Percentage of endpoints with content type application/json | 51 % |
| Info | Informational | http://localhost:8080 | Percentage of endpoints with content type font/woff2 | 19 % |
| Info | Informational | http://localhost:8080 | Percentage of endpoints with content type text/css | 2 % |
| Info | Informational | http://localhost:8080 | Percentage of endpoints with content type text/html | 8 % |
| Info | Informational | http://localhost:8080 | Percentage of endpoints with method GET | 95 % |
| Info | Informational | http://localhost:8080 | Percentage of endpoints with method PATCH | 2 % |
| Info | Informational | http://localhost:8080 | Percentage of endpoints with method POST | 2 % |
| Info | Informational | http://localhost:8080 | Count of total endpoints | 47    |
| Info | Informational | http://localhost:8080 | Percentage of slow responses | 1 % |







## Alerts

| Name | Risk Level | Number of Instances |
| --- | --- | --- |
| Modern Web Application | Informational | 3 |
| Private IP Disclosure | 				False Positives: | 1 |




## Alert Detail



### [ Modern Web Application ](https://www.zaproxy.org/docs/alerts/10109/)



##### Informational (Medium)

### Description

The application appears to be a modern web application. If you need to explore it automatically then the Client Spider may well be more effective than the standard one.

* URL: http://localhost:8080/
  * Node Name: `http://localhost:8080/`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `<script type="module" crossorigin src="/assets/index-BYLIttzU.js"></script>`
  * Other Info: `No links have been found while there are scripts, which is an indication that this is a modern web application.`
* URL: http://localhost:8080/favicon.ico
  * Node Name: `http://localhost:8080/favicon.ico`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `<script type="module" crossorigin src="/assets/index-BYLIttzU.js"></script>`
  * Other Info: `No links have been found while there are scripts, which is an indication that this is a modern web application.`
* URL: http://localhost:8080/sitemap.xml
  * Node Name: `http://localhost:8080/sitemap.xml`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `<script type="module" crossorigin src="/assets/index-BYLIttzU.js"></script>`
  * Other Info: `No links have been found while there are scripts, which is an indication that this is a modern web application.`


Instances: 3

### Solution

This is an informational alert and so no changes are required.

### Reference




#### Source ID: 3

### [ Private IP Disclosure ](https://www.zaproxy.org/docs/alerts/2/)



##### 				False Positives: (False Positive)

### Description

A private IP (such as 10.x.x.x, 172.x.x.x, 192.168.x.x) or an Amazon EC2 private hostname (for example, ip-10-0-56-78) has been found in the HTTP response body. This information might be helpful for further attacks targeting internal systems.

* URL: http://localhost:8080/api/v1/auth/sessions
  * Node Name: `http://localhost:8080/api/v1/auth/sessions`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `172.17.0.1`
  * Other Info: `172.17.0.1
172.17.0.1
172.17.0.1
172.17.0.1
172.17.0.2
`


Instances: 1

### Solution

Remove the private IP address from the HTTP response body. For comments, use JSP/ASP/PHP comment instead of HTML/JavaScript comment which can be seen by client browsers.

### Reference


* [ https://datatracker.ietf.org/doc/html/rfc1918 ](https://datatracker.ietf.org/doc/html/rfc1918)


#### CWE Id: [ 497 ](https://cwe.mitre.org/data/definitions/497.html)


#### WASC Id: 13

#### Source ID: 3


