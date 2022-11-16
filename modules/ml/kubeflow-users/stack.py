#  Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License").
#    You may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import os
import json
from typing import Any, cast, Dict, List

# import cdk_nag
from aws_cdk import CfnJson, Stack, Tags
from aws_cdk import aws_eks as eks
from aws_cdk import aws_iam as iam
from aws_cdk import aws_secretsmanager as secret

# from cdk_nag import NagSuppressions
from constructs import Construct, IConstruct

project_dir = os.path.dirname(os.path.abspath(__file__))

class KubeflowUsersStack(Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        deployment_name: str,
        module_name: str,
        eks_cluster_name: str,
        eks_admin_role_arn: str,
        eks_oidc_arn: str,
        eks_openid_connect_issuer:str,
        users: List[Dict[str, Any]],
        **kwargs: Any,
 ) -> None:

        super().__init__(
            scope,
            id,
            description="This stack creates the Roles to support Kubeflow-on-AWS",
        )

        self.deployment_name = deployment_name
        self.module_name = module_name
        Tags.of(scope=cast(IConstruct, self)).add(key="Deployment", value=f"addf-{self.deployment_name}")

        dep_mod = f"addf-{self.deployment_name}-{self.module_name}"
        dep_mod = dep_mod[:27]

        # Import EKS Cluster
        provider = eks.OpenIdConnectProvider.from_open_id_connect_provider_arn(
            self, f"{dep_mod}-provider", eks_oidc_arn
        )

        eks_cluster = eks.Cluster.from_cluster_attributes(
            self,
            f"{dep_mod}-eks-cluster",
            cluster_name=eks_cluster_name,
            kubectl_role_arn=eks_admin_role_arn,
            open_id_connect_provider=provider,
        )

        kf_profile_sa = eks_cluster.add_service_account(
                f"profiles-controller-sa-{dep_mod}", 
                name="profiles-controller-service-account", 
                namespace="kubeflow"                
        )
        kf_serviceaccount_policy_document_path = os.path.join(
                project_dir, "policies", "iam-profile-sa-policy.json"
            )

        with open(kf_serviceaccount_policy_document_path) as json_file:
            kf_serviceaccount_policy_document_json = json.load(json_file)

        kf_serviceaccount_policy = iam.Policy(
                self,
                "kfserviceaccountbcontrollerpolicy",
                document=iam.PolicyDocument.from_json(kf_serviceaccount_policy_document_json),
            )
        kf_profile_sa.role.attach_inline_policy(kf_serviceaccount_policy)

        for idx, user in enumerate(users):
            s_name = user['secret']
            p_arn=user['policyArn']
            
            secret_entry= secret.Secret.from_secret_name_v2(
                self,
                id = f"secret-{s_name}",
                secret_name =s_name
            )
            if secret_entry:
                #u_name = secret_entry.secret_value_from_json('username').to_string()
                string_aud = CfnJson(
                    self,
                    f"ConditionJsonAud-{idx}",
                    value={f"{eks_openid_connect_issuer}:aud": "sts.amazon.com"}
                )
                role_name = f"addf-{self.deployment_name}-{self.module_name}-{self.region}-{idx}"
                kf_user_role= iam.Role(
                    self,
                    id=f"role-{idx}",
                    role_name=role_name,
                    assumed_by=iam.OpenIdConnectPrincipal(
                                provider,
                                conditions={"StringEquals": string_aud},
                                ),                         
                    managed_policies=[
                        iam.ManagedPolicy.from_managed_policy_arn(
                            self,
                            id=f"managed-polcy-{idx}",
                            managed_policy_arn=p_arn)
                    ],
                )

                # kf_user_role.assume_role_policy.add_statements(
                #         iam.PolicyStatement(
                #         effect=iam.Effect.ALLOW,
                #         actions=["sts:AssumeRoleWithWebIdentity"],
                #         principals=[
                #             iam.OpenIdConnectPrincipal(
                #                 provider,
                #                 conditions={"StringEquals": string_aud},
                #                 )                          
                #             ]
                #         )
        
                # )
                user['roleArn'] = kf_user_role.role_arn
        self.kf_users = users




