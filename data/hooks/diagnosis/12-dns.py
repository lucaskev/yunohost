#!/usr/bin/env python

import os

from moulinette.utils.network import download_text
from moulinette.utils.process import check_output
from moulinette.utils.filesystem import read_file

from yunohost.diagnosis import Diagnoser
from yunohost.domain import domain_list, _build_dns_conf, _get_maindomain

class DNSDiagnoser(Diagnoser):

    id_ = os.path.splitext(os.path.basename(__file__))[0].split("-")[1]
    description = "dns_configurations"
    cache_duration = 3600*24

    def validate_args(self, args):
        all_domains = domain_list()["domains"]
        if "domain" not in args.keys():
            return { "domains" : all_domains }
        else:
            assert args["domain"] in all_domains, "Unknown domain"
            return { "domains" : [ args["domain"] ] }

    def run(self):

        resolvers = read_file("/etc/resolv.dnsmasq.conf").split("\n")
        ipv4_resolvers = [r.split(" ")[1] for r in resolvers if r.startswith("nameserver") and ":" not in r]
        # FIXME some day ... handle ipv4-only and ipv6-only servers. For now we assume we have at least ipv4
        assert ipv4_resolvers != [], "Uhoh, need at least one IPv4 DNS resolver ..."

        self.resolver = ipv4_resolvers[0]
        main_domain = _get_maindomain()

        for domain in self.args["domains"]:
            self.logger_info("Diagnosing DNS conf for %s" % domain)
            for report in self.check_domain(domain, domain==main_domain):
                yield report

    def check_domain(self, domain, is_main_domain):

        expected_configuration = _build_dns_conf(domain)

        # Here if there are no AAAA record, we should add something to expect "no" AAAA record
        # to properly diagnose situations where people have a AAAA record but no IPv6

	for category, records in expected_configuration.items():

            discrepancies = []

            for r in records:
                current_value = self.get_current_record(domain, r["name"], r["type"]) or "None"
                expected_value = r["value"] if r["value"] != "@" else domain+"."

                if current_value == "None":
                    discrepancies.append(("diagnosis_dns_missing_record", (r["type"], r["name"], expected_value)))
                elif current_value != expected_value:
                    discrepancies.append(("diagnosis_dns_discrepancy", (r["type"], r["name"], expected_value, current_value)))

            if discrepancies:
                if category == "basic" or is_main_domain:
                    level = "ERROR"
                else:
                    level = "WARNING"
                report = (level, "diagnosis_dns_bad_conf", {"domain": domain, "category": category})
            else:
                level = "SUCCESS"
                report = ("SUCCESS", "diagnosis_dns_good_conf", {"domain": domain, "category": category})
                details = None

            output = dict(meta = {"domain": domain, "category": category},
                          result = level,
                          report = report )

            if discrepancies:
                output["details"] = discrepancies

            yield output


    def get_current_record(self, domain, name, type_):
        if name == "@":
            command = "dig +short @%s %s %s" % (self.resolver, type_, domain)
        else:
            command = "dig +short @%s %s %s.%s" % (self.resolver, type_, name, domain)
        output = check_output(command).strip()
        output = output.replace("\;",";")
        if output.startswith('"') and output.endswith('"'):
            output = '"' + ' '.join(output.replace('"',' ').split()) + '"'
        return output


def main(args, env, loggers):
    return DNSDiagnoser(args, env, loggers).diagnose()

